import base64
import logging
import re
from typing import Any

from google import genai
from google.genai import types
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from schemas import (
    DialogueState,
    OperatorTurnAnalysis,
    RoadCode,
    RunTaskRequest,
    RunTaskResponse,
    TurnObjective,
)
from services.audit_service import AuditService, generate_session_id
from services.centrala_service import CentralaService
from services.policy_engine import PolicyEngine
from services.prompt_builder import PromptBuilder
from services.tts_service import TTSService

logger = logging.getLogger("services.orchestrator")


def extract_text_from_ai_message(content: Any) -> str:
    """Extracts plain text string from str, list of strings/dicts, or structured AIMessage content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and "text" in item or "text" in item:
                    parts.append(str(item["text"]))
            elif hasattr(item, "text"):
                parts.append(str(getattr(item, "text", "")))
        return "".join(parts)
    return str(content) if content is not None else ""


class ConversationalOrchestrator:
    """Manages the interactive multi-turn telephone conversation with Centrala."""

    def __init__(
        self,
        request: RunTaskRequest,
        audit_service: AuditService | None = None,
        centrala_service: CentralaService | None = None,
        tts_service: TTSService | None = None,
    ) -> None:
        self.request = request
        self.session_id = request.session_id or generate_session_id(request.backend)
        self.audit = audit_service or AuditService()
        self.centrala = centrala_service or CentralaService()
        self.tts = tts_service or TTSService(
            voice_name=request.voice_name, speaking_rate=request.speaking_rate
        )

        self.model_name = request.model or config.GEMINI_MODEL
        self.thinking_level = request.thinking_level or config.THINKING_LEVEL

        # Initialize Google GenAI client for direct multimodal audio understanding
        self.genai_client = genai.Client(
            vertexai=True,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
        )

        # Initialize ChatGoogleGenerativeAI for conditioned speech text generation
        self.speech_llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
            vertexai=True,
            temperature=0.2,
            thinking_level=self.thinking_level,
        )

    async def analyze_operator_audio(
        self, audio_bytes: bytes, last_agent_message: str | None = None
    ) -> OperatorTurnAnalysis:
        """Transcribes and extracts behavioral/mission facts from operator audio in a single multimodal call."""
        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/mp3")

        prompt_text = (
            "Posłuchaj uważnie wypowiedzi operatora systemu OKO. "
            "Jesteś agentem wywiadu analizującym meldunek radiowo-telefoniczny.\n\n"
            "ZADANIA:\n"
            "1. Dokonaj wiernej, dosłownej transkrypcji słów operatora w języku polskim.\n"
            "2. Przeanalizuj każde zdanie pod kątem sentymentu, ironii, humoru oraz tematu.\n"
            "3. Określ ogólny sentyment oraz poziom podejrzeń operatora (suspicion_level: low/medium/high/critical).\n"
            "4. Zidentyfikuj czy operator zażądał hasła, kodu lub weryfikacji tożsamości (auth_requested).\n"
            "5. Wyodrębnij statusy dróg RD224, RD472, RD820 (passable, blocked, contaminated, unknown) oraz uzasadnienia.\n"
            "6. Sprawdź czy operator potwierdził wyłączenie monitoringu (monitoring_disabled_confirmed).\n"
            "7. Określ call_burned: ustaw True TYLKO JEŚLI operator jawnie zakończył rozmowę (odłożył słuchawkę, ogłosił alarm, "
            "nazwał nas szpiegiem/oszustem lub odmówił kontaktu). Zwykłe wahanie, pytanie o hasło BARBAKAN lub pytanie 'po co wyłączamy monitoring' to bezwzględnie False!\n"
            "8. W polu reasoning krótko uzasadnij swoje wnioski."
        )

        if last_agent_message:
            prompt_text += f'\n\nKontekst: Nasza ostatnia wypowiedź do operatora brzmiała: "{last_agent_message}"'

        logger.info(
            f"Analyzing inbound audio ({len(audio_bytes)} bytes) with {self.model_name}..."
        )

        response = self.genai_client.models.generate_content(
            model=self.model_name,
            contents=[audio_part, prompt_text],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OperatorTurnAnalysis,
                temperature=0.1,
            ),
        )

        raw_text = response.text or "{}"
        try:
            analysis = OperatorTurnAnalysis.model_validate_json(raw_text)
            logger.info(
                f"Operator transcript: '{analysis.operator_transcript}' "
                f"(sentiment={analysis.overall_sentiment}, suspicion={analysis.suspicion_level}, "
                f"roads={analysis.road_statuses}, auth_requested={analysis.auth_requested}, call_burned={analysis.call_burned})"
            )
            return analysis
        except Exception as e:
            logger.error(
                f"Failed to parse OperatorTurnAnalysis JSON: {e}, raw: {raw_text[:300]}"
            )
            # Safe deterministic fallback
            return OperatorTurnAnalysis(
                operator_transcript="[Błąd parsowania audio operatora]",
                overall_sentiment="neutral",
                suspicion_level="low",
                reasoning=f"Parsing error: {e}",
            )

    async def generate_speech_ssml(
        self,
        state: DialogueState,
        objective: TurnObjective,
        last_operator_utterance: str | None = None,
    ) -> str:
        """Generates natural Polish speech text formatted in SSML conditioned on the TurnObjective."""
        prompt = PromptBuilder.build_speech_prompt(
            state=state,
            objective=objective,
            last_operator_utterance=last_operator_utterance,
        )

        logger.info(f"Generating speech for objective: {objective}")
        try:
            ai_msg = await self.speech_llm.ainvoke(prompt)
            content = extract_text_from_ai_message(ai_msg.content)
        except Exception as e:
            logger.warning(
                f"speech_llm invoke error: {e}, falling back to genai_client"
            )
            content = ""

        if not content.strip():
            logger.info(
                "Speech content from speech_llm was empty; generating via genai_client..."
            )
            try:
                genai_resp = self.genai_client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                content = genai_resp.text or ""
            except Exception as e:
                logger.error(f"genai_client fallback error: {e}")

        # Clean up code blocks if model wrapped SSML in ```xml ... ```
        cleaned = re.sub(
            r"^```(?:xml|html|ssml)?\s*", "", content.strip(), flags=re.IGNORECASE
        )
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())

        # Strip existing speak tags if any to check inner content
        inner_content = re.sub(r"^<speak>\s*", "", cleaned, flags=re.IGNORECASE)
        inner_content = re.sub(
            r"\s*</speak>$", "", inner_content, flags=re.IGNORECASE
        ).strip()

        # Deterministic mission guardrail: never emit empty speech
        if not inner_content:
            logger.warning(
                f"Inner speech content was empty for {objective}! Applying deterministic mission fallback."
            )
            if objective == "SEND_OPENING_MESSAGE":
                inner_content = "Dzień dobry, z tej strony Tymon Gajewski, oficer logistyki Zygfryda."
            elif objective == "INQUIRE_ROAD_STATUSES":
                inner_content = (
                    "Dzwonię w sprawie transportu organizowanego do jednej z baz Zygfryda. "
                    "Chciałbym zapytać o aktualny status dróg RD224, RD472 oraz RD820 – która z nich jest przejezdna?"
                )
            elif objective == "ANSWER_AUTH_CHALLENGE":
                inner_content = "Tajne hasło operatorów to BARBAKAN."
            elif objective == "EXPLAIN_FOOD_LEGEND":
                inner_content = (
                    "To w ramach transportu żywności do jednej z tajnych baz Zygfryda. "
                    "Nie możemy ujawnić jej lokalizacji, dlatego ta misja nie może figurować w logach."
                )
            elif objective == "REQUEST_MONITORING_DEACTIVATION":
                target_road = state.selected_evacuation_road or "RD472"
                inner_content = f"Proszę o natychmiastowe wyłączenie monitoringu na trasie {target_road}."
            else:
                inner_content = "Dziękuję, potwierdzam wykonanie zadania."

        final_ssml = f"<speak>{inner_content}</speak>"
        logger.info(f"Final SSML content: {final_ssml[:150]}...")
        return final_ssml

    async def run(self) -> RunTaskResponse:
        """Executes the full conversational lifecycle with Centrala."""
        self.audit.ensure_table()
        state = DialogueState()
        restarts_used = 0

        await self.audit.alog_event(
            session_id=self.session_id,
            actor="orchestrator",
            content=f"Starting phonecall session {self.session_id} (max_iterations={self.request.max_iterations})",
            metadata={
                "request": self.request.model_dump(),
                "max_restarts": self.request.max_restarts,
            },
        )

        last_agent_message: str | None = None

        while restarts_used <= self.request.max_restarts:
            # Step 1: Start conversation session with Centrala
            logger.info(
                f"Initiating conversation start with Centrala (restart #{restarts_used})..."
            )
            start_resp = await self.centrala.start_call()

            # Check if Centrala returned an initial error
            code = start_resp.get("code")
            msg_str = str(start_resp.get("message", ""))
            is_start_error = False

            if (
                code is not None
                and code < 0
                or (
                    "error" in msg_str.lower()
                    and "session started" not in msg_str.lower()
                )
            ):
                is_start_error = True

            if is_start_error:
                error_msg = msg_str or "Centrala start error"
                logger.error(f"Centrala start failed: {error_msg}")
                if restarts_used < self.request.max_restarts:
                    restarts_used += 1
                    continue
                return RunTaskResponse(
                    status="FAILED",
                    session_id=self.session_id,
                    turns_completed=state.turn_count,
                    restarts_used=restarts_used,
                    selected_road=state.selected_evacuation_road,
                    monitoring_disabled=state.monitoring_deactivation_confirmed,
                    error=f"Centrala start failed: {error_msg}",
                    reasoning="Could not start session with Centrala verification endpoint",
                )

            # Reset turn state for the new session
            state = DialogueState()
            last_agent_message = None

            # Handle possible audio in start response (e.g. operator picking up receiver)
            start_audio = start_resp.get("audio")
            last_operator_utterance: str | None = None
            if start_audio and isinstance(start_audio, str):
                try:
                    audio_bytes = base64.b64decode(start_audio)
                    analysis = await self.analyze_operator_audio(audio_bytes)
                    last_operator_utterance = analysis.operator_transcript
                    self._update_state_from_analysis(state, analysis)
                except Exception as e:
                    logger.warning(f"Could not parse initial audio in start_resp: {e}")

            # Step 2: Main Turn Loop
            session_success = False

            while state.turn_count < self.request.max_iterations:
                state.turn_count += 1
                current_turn = state.turn_count
                logger.info(f"--- [Turn {current_turn}] ---")

                # 1. Determine next objective
                objective = PolicyEngine.determine_next_objective(state)

                # 2. Generate SSML speech
                ssml_text = await self.generate_speech_ssml(
                    state=state,
                    objective=objective,
                    last_operator_utterance=last_operator_utterance,
                )
                last_agent_message = ssml_text

                # Update state milestone flags for actions Tymon takes
                if objective == "SEND_OPENING_MESSAGE":
                    state.opening_message_sent = True
                elif objective == "ANSWER_AUTH_CHALLENGE":
                    state.auth_code_provided = True
                    state.auth_requested = False
                elif objective == "EXPLAIN_FOOD_LEGEND":
                    state.food_legend_used = True
                    state.operator_suspicious = False
                elif objective == "REQUEST_MONITORING_DEACTIVATION":
                    state.monitoring_deactivation_requested = True

                # 3. Synthesize audio via Google Cloud TTS
                mp3_base64 = self.tts.synthesize_base64_mp3(
                    text_or_ssml=ssml_text,
                    voice_name=self.request.voice_name,
                    speaking_rate=self.request.speaking_rate,
                )

                state.conversation_history.append(
                    f"Tymon: {re.sub(r'<[^>]+>', '', ssml_text).strip()}"
                )

                await self.audit.alog_event(
                    session_id=self.session_id,
                    actor="agent",
                    content=f"Turn {current_turn} [Tymon -> Operator]: {re.sub(r'<[^>]+>', '', ssml_text).strip()}",
                    metadata={
                        "turn": current_turn,
                        "objective": objective,
                        "ssml": ssml_text,
                    },
                )

                # 4. Transmit audio turn to Centrala
                turn_resp = await self.centrala.send_audio_turn(mp3_base64)

                # Check if Centrala returned the flag directly!
                msg = str(turn_resp.get("message", ""))
                flag_match = re.search(r"\{FLG:[^}]+\}", msg)
                if flag_match:
                    flag = flag_match.group(0)
                    state.mission_flag = flag
                    state.monitoring_deactivation_confirmed = True
                    session_success = True
                    logger.info(f"MISSION SUCCESS! Course flag acquired: {flag}")
                    await self.audit.alog_event(
                        session_id=self.session_id,
                        actor="system",
                        content="Course flag acquired successfully",
                        metadata={"flag": flag, "turn": current_turn},
                    )
                    break

                # Dual-Source Call Burn Check 1: Transport Level
                turn_code = turn_resp.get("code")
                has_audio = bool(turn_resp.get("audio"))
                is_transport_error = False

                if turn_code is not None and turn_code < 0 or not has_audio:
                    is_transport_error = True

                if is_transport_error:
                    logger.warning(
                        f"Centrala returned error or missing audio: {turn_resp}. Flagging call_burned."
                    )
                    state.call_burned = True
                    break

                # 5. Multimodal Extraction of Inbound Operator Audio
                inbound_audio_b64 = str(turn_resp.get("audio", ""))
                try:
                    inbound_bytes = base64.b64decode(inbound_audio_b64)
                    analysis = await self.analyze_operator_audio(
                        inbound_bytes, last_agent_message=last_agent_message
                    )
                    last_operator_utterance = analysis.operator_transcript
                    state.conversation_history.append(
                        f"Operator: {analysis.operator_transcript}"
                    )

                    await self.audit.alog_event(
                        session_id=self.session_id,
                        actor="operator",
                        content=f"Turn {current_turn} [Operator -> Tymon]: {analysis.operator_transcript}",
                        metadata={
                            "turn": current_turn,
                            "sentiment": analysis.overall_sentiment,
                            "suspicion": analysis.suspicion_level,
                            "roads": analysis.road_statuses,
                            "auth_requested": analysis.auth_requested,
                            "call_burned": analysis.call_burned,
                        },
                    )

                    # Dual-Source Call Burn Check 2: Semantic Level
                    if analysis.call_burned:
                        logger.warning(
                            f"Operator semantically burned call: {analysis.call_burned_reason}"
                        )
                        state.call_burned = True
                        break

                    self._update_state_from_analysis(state, analysis)

                except Exception as e:
                    logger.error(f"Error handling operator audio response: {e}")
                    state.call_burned = True
                    break

                # Check if flag appeared in message during turn
                if "{FLG:" in str(turn_resp.get("message", "")):
                    flag_match = re.search(
                        r"\{FLG:[^}]+\}", str(turn_resp.get("message", ""))
                    )
                    if flag_match:
                        state.mission_flag = flag_match.group(0)
                        session_success = True
                        break

            if session_success:
                return RunTaskResponse(
                    status="SUCCESS",
                    session_id=self.session_id,
                    turns_completed=state.turn_count,
                    restarts_used=restarts_used,
                    selected_road=state.selected_evacuation_road,
                    monitoring_disabled=state.monitoring_deactivation_confirmed,
                    flag=state.mission_flag,
                    reasoning=f"Mission accomplished in {state.turn_count} turns on road {state.selected_evacuation_road}",
                )

            # If call was burned and we have remaining restarts, loop again
            if state.call_burned and restarts_used < self.request.max_restarts:
                restarts_used += 1
                logger.warning(
                    f"Call was burned. Restarting session (attempt {restarts_used}/{self.request.max_restarts})..."
                )
                continue

            break

        return RunTaskResponse(
            status="FAILED",
            session_id=self.session_id,
            turns_completed=state.turn_count,
            restarts_used=restarts_used,
            selected_road=state.selected_evacuation_road,
            monitoring_disabled=state.monitoring_deactivation_confirmed,
            error="Call burned or maximum turns exceeded",
            reasoning=f"Conversation did not complete successfully after {restarts_used} restarts",
        )

    def _update_state_from_analysis(
        self, state: DialogueState, analysis: OperatorTurnAnalysis
    ) -> None:
        """Updates DialogueState milestone slots from structured extraction."""
        # 1. Update road statuses
        for obs in analysis.roads:
            if obs.road in state.roads:
                if obs.status != "unknown":
                    state.roads[obs.road].status = obs.status
                if obs.justification:
                    state.roads[obs.road].operator_justification = obs.justification

        # 2. Check for single passable road (or elimination if 2 are blocked/contaminated)
        passable_roads: list[RoadCode] = [
            r_code
            for r_code, r_assessment in state.roads.items()
            if r_assessment.status == "passable"
        ]
        if len(passable_roads) == 1:
            state.selected_evacuation_road = passable_roads[0]
            logger.info(
                f"Identified single safe evacuation road to Syjon: {state.selected_evacuation_road}"
            )
        elif not state.selected_evacuation_road:
            non_passable = [
                r_code
                for r_code, r_assessment in state.roads.items()
                if r_assessment.status in ("blocked", "contaminated")
            ]
            if len(non_passable) == 2:
                for r_code in state.roads:
                    if r_code not in non_passable:
                        state.selected_evacuation_road = r_code
                        state.roads[r_code].status = "passable"
                        logger.info(
                            f"Identified single remaining safe evacuation road to Syjon by elimination: {state.selected_evacuation_road}"
                        )
                        break

        # 3. Update authorization challenge
        if analysis.auth_requested:
            state.auth_requested = True
            logger.info("Operator requested authorization clearance!")

        # 4. Update suspicion
        if analysis.suspicion_level in (
            "high",
            "critical",
        ) or analysis.overall_sentiment in ("suspicious", "hostile"):
            state.operator_suspicious = True
            logger.info(
                f"Elevated operator suspicion detected: {analysis.suspicion_level}"
            )

        # 5. Update monitoring deactivation confirmed
        if analysis.monitoring_disabled_confirmed:
            state.monitoring_deactivation_confirmed = True
            if state.selected_evacuation_road:
                state.roads[state.selected_evacuation_road].monitoring = "disabled"
            logger.info("Operator confirmed monitoring deactivated on selected road!")
