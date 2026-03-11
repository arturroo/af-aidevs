---
title: Programowanie interakcji z modelem językowym
space_id: 2476415
status: scheduled
published_at: '2026-03-09T04:00:00Z'
is_comments_enabled: true
is_liking_enabled: true
skip_notifications: false
cover_image: 'https://cloud.overment.com/Hero_navigating_the_node_realm-1772725379.png'
circle_post_id: 30339505
---

![https://vimeo.com/1169549431](https://vimeo.com/1169549431)

Cześć! Miło mi powitać Cię w AI_devs 4: Builders. To szkolenie, w którym poprzez budowanie gotowych produkcyjnie rozwiązań przekonamy się, co może, a czego nie może generatywna sztuczna inteligencja.

Mam na imię Adam i przygotowałem dla Ciebie tę oraz wszystkie kolejne lekcje. Na końcu każdej z nich znajdziesz zadania praktyczne i element fabularny opracowane przez Jakuba i Mateusza. 

> Informacja: Przez cały czas trwania szkolenia jesteśmy także dostępni dla Was w komentarzach. Wsparcie dotyczące realizacji zadań możecie uzyskać także od naszych absolwentów: Pawła Dulaka (Dulare), Grzegorza Cymborskiego oraz Grzegorza Ćwiklińskiego. Natomiast mój nick możecie oznaczać w pytaniach dotyczących treści lekcji oraz dołączonych przykładów kodu.

Zaczynajmy!

## Sterowanie zachowaniem modelu z pomocą kodu
Modele Językowe (eng. large language models, LLM) mogą stanowić część logiki aplikacji, przetwarzając dane w postaci tekstu, obrazu, audio czy wideo, dzięki interakcji za pośrednictwem API. Oznacza to, że **możemy sterować ich zachowaniem z pomocą kodu**, co przekłada się na większe możliwości pracy z danymi, których wykorzystanie w logice aplikacji było trudne, bądź niekiedy niemożliwe. 

Dzieje się to jednak kosztem utraty pełnej kontroli, ponieważ LLM nie dają gwarancji, że nawet dla tych samych danych wejściowych, otrzymamy ten sam wynik za każdym razem. Mówiąc inaczej: **programowanie generatywnych aplikacji wiąże się z łączeniem deterministycznej natury kodu z niedeterministycznymi wynikami zwracanymi przez modele AI** (choć kiedyś może się to zmienić - "[Defeating Nondeterminism in LLM Inference](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)" ~ Thinking Machines). O tym, co to dokładnie oznacza, najlepiej przekonać się w praktyce. 

Dostęp do modeli przez API oferowany jest między innymi przez **[OpenAI](https://platform.openai.com/api-keys), [Anthropic](https://console.anthropic.com/settings/keys) czy [Gemini](https://aistudio.google.com/api-keys)**, a także przez platformy takie jak **[OpenRouter](https://openrouter.ai/settings/keys)**, [Amazon Bedrock](https://aws.amazon.com/bedrock/) czy [Microsoft Azure](https://azure.microsoft.com/en-us/solutions/ai) (często produkcyjnie).  W AI_devs 4 pojawią się przykłady z platform, których są wyróżnione pogrubionym fontem. Dzięki temu doświadczymy różnic pomiędzy ich interfejsem oraz dostępnymi modelami. Ogólne zasady wszędzie pozostają jednak takie same, dlatego zaczniemy od fundamentów.

Z matematycznego punktu widzenia model językowy jest funkcją, która dla otrzymanych danych wylicza możliwe dalsze ciągi i ich prawdopodobieństwa. Spośród nich **wybierany jest pojedynczy „token"** (często z elementem losowym), co sprawia, że wynik końcowy pozostaje **niedeterministyczny**. Proces ten uruchomiony w pętli buduje odpowiedź krok po kroku, aż do wybrania tokenu sygnalizującego jej zakończenie.

Poniższa wizualizacja ilustruje proces generowania kolejnych tokenów (fragmentów) i pokazuje również, że jest on **autoregresyjny**. Czyli przy tworzeniu kolejnych fragmentów pod uwagę brane są zarówno **dane wejściowe**, jak i **cała dotychczas wygenerowana treść**, a wygenerowany token **nie może zostać usunięty** ([przynajmniej na ten moment](https://huggingface.co/papers/2602.08676)). Oznacza to, że na jakość wypowiedzi modelu wpływa nie tylko to, co mówi użytkownik, ale także treść generowana przez AI oraz instrukcje dostarczone przez developera w formie tzw. instrukcji systemowej (bądź promptu systemowego).

![](https://cloud.overment.com/2026-01-14/ai_devs_4_autoregression-7af4f432-b.png)

API modeli językowych jest bezstanowe (choć po części zmieniają to Interactions API oraz Responses API, ale tylko powierzchownie). Oznacza to, że **każdorazowo przesyłamy komplet danych**, które model ma przetworzyć. Obowiązuje nas jednak limit określany jako okno kontekstowe (eng. Context Window) wyrażone w **tokenach**, który obejmuje **wszystkie dane, które w danej chwili przetwarza model** z konieczną przestrzenią na tokeny, które są generowane.

Poniżej widać jak informacje w postaci **promptu systemowego, wiadomości użytkownika** oraz **odpowiedzi modelu** są tokenizowane. Wśród tokenów pojawiają się także tokeny specjalne, których celem jest ustrukturyzowanie sekwencji (`<|im_start|>` i `<|im_end|>` oznaczają początek i koniec wiadomości). Widzimy także, że z perspektywy modelu tokeny te mają postać liczbowych identyfikatorów, ponieważ jest to format na którym operuje model.

![Tokenizacja polega na zamianie treści na tokeny, których identyfikatory przetwarzają modele AI](https://cloud.overment.com/2026-01-14/ai_devs_4_tokens-c0e7019d-3.png)

Sposób podziału treści na tokeny zależy od tokenizatora z którego korzysta dany model. Tokenami mogą być fragmenty słów, całe słowa, znaki interpunkcyjne czy spacje. Podział uzależniony jest między innymi od częstotliwości występowania w danych treningowych. Natomiast celem jest efektywne przetwarzanie danych. 

Przykładowo "Hello" to pojedynczy token, ponieważ występuje często w (głównie angielskich) danych treningowych. Natomiast "Cześć" to zwykle trzy tokeny, ponieważ polski tekst zwykle jest słabiej reprezentowany. W praktyce oznacza to, że posługując się językiem polskim przy pracy z modelami, przetwarzamy ~50-70% więcej tokenów za które płacimy więcej, a proces generowania trwa dłużej.

Sam sposób podziału treści na tokeny można sprawdzić z pomocą narzędzia [Tiktokenizer](https://tiktokenizer.vercel.app/). Wystarczy wprowadzić w nim kilka przykładowych wiadomości, aby zobaczyć jak zostają one dzielone na poszczególne tokeny.

Zatem na ten moment wiemy, że:

- **Tokeny**: Modele przetwarzają treść w formie liczbowej. Liczby te są identyfikatorami tokenów, czyli fragmentów, z których składają się całe wypowiedzi. 
- **Inferencja i Autoregresja:** Modele generują dane poprzez przewidywanie kolejnego tokenu na podstawie dotychczasowej treści. Z tego powodu wszystko, co znajduje się w kontekście, wpływa na otrzymany rezultat.
- **Stan:** API modeli jest bezstanowe, więc każdorazowo musimy przesyłać komplet danych niezbędnych do wygenerowania odpowiedzi.
- **Kontekst:** Programistycznie kontrolujemy treść zapytania, dzięki czemu mamy wpływ na dane trafiające do modelu, co w dużym stopniu pozwala nam sterować jego zachowaniem.

Budowanie zapytań po stronie kodu pozwala dość swobodnie manipulować kontekstem pomiędzy zapytaniami. Widać to poniżej, gdzie w pierwszym żądaniu zadanie modelu polegało jedynie na **klasyfikacji zapytania**, a drugie **wykorzystało rezultat poprzedniego** dostosowując prompt tak, aby model poprowadził użytkownika przez proces realizacji zwrotu produktu. 

![](https://cloud.overment.com/2026-01-14/ai_devs_4_routing-ab6c0ada-b.png)

Z perspektywy użytkownika to nadal może być prosta interakcja **pytanie → odpowiedź**. Natomiast dla nas to podejście daje większą kontrolę nad kontekstem oraz zarządzeniem uwagą modelu, co zwykle przekłada się na większą skuteczność ale też z kosztem - wydłużonym czasem reakcji oraz wzrostem kosztów.

Kluczowa lekcja jest następująca: **sterowanie zachowaniem modelu za pomocą kodu polega na zarządzaniu kontekstem i obejmuje możliwość tworzenia wielu zapytań, których wyniki mogą być wykorzystywane pomiędzy sobą.**

Przejdźmy teraz do pierwszej interakcji z modelem językowym, korzystając przy tym z API OpenAI lub OpenRouter ([zaloguj się](https://openrouter.ai/settings/keys), doładuj konto kwotą np. $5 i pobierz klucz API). Aby w pełni zobaczyć zasady, które nas obowiązuję, przejdziemy przez prosty skrypt. Uwaga: w przypadku najnowszych modeli, konieczne jest także potwierdzenie konta dokumentem tożsamości. Można więc skorzystać ze starszych modeli (np. GPT-4.1). 

Poniższy kod wysyła zapytanie do OpenAI, przekazując listę wiadomości konwersacji pomiędzy użytkownikiem i asystentem. Po każdej interakcji, odpowiedź modelu zostaje dopisana do wątku dzięki czemu budujemy kontekst kolejnych zapytań. W rezultacie otrzymujemy efekt rozmowy z AI, którą charakteryzują się czatboty. 

![](https://cloud.overment.com/2026-01-20/ai_devs_4_interaction-b3ae63e2-a.png)

Kod źródłowy dla powyższej interakcji dostępny jest w przykładzie [01_01_interaction](https://github.com/i-am-alice/4th-devs/tree/main/01_01_interaction).

Jest to jednak prosta interakcja, która obecnie ma raczej niewiele wspólnego z narzędziami, które będziemy budować. Jednocześnie pokazuje ona coś ważnego, czyli **programistyczną kontrolę** jaką mamy nad przebiegiem konwersacji i tym samym wpływ na zachowanie samego modelu bądź modeli. Najciekawsze jest jednak to, że naszym celem będzie oddanie dużej części tej kontroli w ręce modelu, czy raczej agentów AI o których powiemy sobie później. Na ten moment wystarczy, że przez słowo **agent** będziemy rozumieć LLM zdolny do elastycznej interakcji z otoczeniem, np. aplikacjami.
## Strukturyzowanie odpowiedzi oraz JSON Schema
Obecność Modeli Językowych w kodzie wymaga strukturyzowania ich wypowiedzi w celu ich dalszego przetwarzania. Mowa o zastosowaniu formatu JSON, którego struktura będzie uzależniona od ustalonego schematu. Popularne API (OpenAI, Anthropic, Gemini) oferują dwa sposoby na otrzymanie odpowiedzi w formacie JSON. Są to: **Structured Outputs** oraz **Function Calling** i teraz skupimy się na tym pierwszym.

API [OpenAI](https://platform.openai.com/docs/guides/structured-outputs) wymaga podania właściwości `text` wskazującej na format `json_schema` oraz pola `schema`, które zawiera strukturę zgodną z ograniczoną wersją JSON Schema, opisaną w dokumentacji [OpenAI](https://platform.openai.com/docs/guides/structured-outputs#supported-schemas), [Anthropic](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) czy [Gemini](https://ai.google.dev/gemini-api/docs/structured-output?example=recipe). W wówczas w odpowiedzi otrzymujemy tekst (JSON String), który można sparsować przy użyciu natywnych funkcji języka programowania, w którym pracujemy.

![](https://cloud.overment.com/2026-01-14/ai_devs_4_structured-39c12447-3.png)

Zatem **Structured Output** pozwala transformować **nieustrukturyzowane dane** (np. notatkę, nagranie, obraz) w niemal dowolny sposób, np.:

- wnioskowanie: udzielanie odpowiedzi na podstawie dostarczonych dokumentów
- ekstrakcja: pobieranie informacji bezpośrednio z treści dokumentów
- kompresja: usuwanie zbędnych treści w celu optymalizacji formy i/lub przekazu
- wzbogacenie: uzupełnianie bądź rozszerzanie treści w istniejącym dokumencie
- parafraza: przepisanie treści przy zachowaniu oryginalnego znaczenia
- tłumaczenie: zmiana języka lub reprezentacji przy zachowaniu oryginalnego znaczenia
- klasyfikacja: przypisanie tagów bądź kategorii według ustalonych zasad
- weryfikacja: ocena treści pod kątem ustalonych kryteriów
- generowanie: tworzenie dokumentów od podstaw
- synteza: tworzenie nowych dokumentów na podstawie istniejących
- ...i inne.

Niemal każdy z powyższych punktów trudno zrealizować z pomocą samego kodu. Jednocześnie z pomocą kodu możemy sterować LLM'em, który wykona te zadania nawet w sposób automatyczny bądź częściowo automatyczny (ponieważ konieczna będzie weryfikacja). 

JSON Schema dołączony do zapytania API należy rozumieć na dwa sposoby:

1. **Struktura:** W trybach `strict` jest gwarantowana, czyli mamy pewność, że odpowiedź modelu będzie mieć dokładnie taki kształt, jakiego oczekujemy.
2. **Wartości:** Są one generowane przez model na podstawie **treści** (`input`) oraz **nazw** i **opisów**. Muszą więc być one **zrozumiałe** a jednocześnie **zwięzłe**, aby zwiększyć prawdopodobieństwo otrzymania oczekiwanych rezultatów.

Punkt drugi jest szczególnie ważny, ponieważ jest bardzo często pomijany przy projektowaniu narzędzi oraz agentów AI. Warto pamiętać, że przy projektowaniu JSON Schema **może pomóc LLM**, ale (przynajmniej obecnie) musimy samodzielnie zadbać o finalną jakość opisów i nazw. 

![](https://cloud.overment.com/2026-01-16/ai_devs_4_schema-739091a9-9.png)

Przykład kodu przedstawiający pracę z **Structured Outputs** znajduje się w [01_01_structured](https://github.com/i-am-alice/4th-devs/tree/main/01_01_structured).

Warto także uwzględnić wartości **nieznane** bądź **neutralne**. W powyższym przykładzie detekcji sentymentu, oprócz wartości "pozytywny" i "negatywny" uwzględniam także "neutralny", "mieszany" oraz "nieznany". Takie podejście zwykle zwiększa skuteczność i obniża ryzyko halucynacji (bądź też bardziej konfabulacji), ponieważ nie zmuszamy modelu do określenia sentymentu w sytuacji gdy nie da się tego zrobić.  

Istotna jest także **kolejność** generowanych właściwości ze względu na fakt, że **poprzedzające tokeny wpływają na sposób dobierania kolejnych**. Zatem "reasoning" generowany jako pierwszy, wpłynie na określenie "sentiment", a ten na ocenę "confidence". 

Structured Outputs staje się więc kluczowym elementem LLM API z którego będziemy korzystać bardzo często zaraz obok Function Calling. Temat ten omówimy jednak nieco później.
## Formatowanie i renderowanie odpowiedzi LLM oraz LRM
Wyświetlenie odpowiedzi LLM w teorii jest banalne, lecz w praktyce okazuje się znacznie bardziej złożone. Odpowiedź może składać się z tokenów rozumowania (niekiedy jedynie z podsumowania), tokenów sygnalizujących korzystanie z natywnych narzędzi oraz wywołań funkcji (function calling), a także z generowanych obrazów, tekstu docelowego czy informacji o błędach. Nie chodzi zatem o zwykłą interakcję **pytanie - odpowiedź** lecz serię **zdarzeń**, które musimy obsłużyć. W przypadku OpenAI zostały one opisane w [Streaming Events](https://developers.openai.com/api/reference/resources/responses/streaming-events), natomiast w praktyce będzie nam zależało na dodaniu także własnych zdarzeń (np. żądanie potwierdzenia akcji).

![](https://cloud.overment.com/2026-01-17/ai_devs_4_rendering-a56a8eff-8.png)

Treść odpowiedzi może być także **strumieniowana**, a sam proces wstrzymywany w celu uzyskania potwierdzenia od użytkownika bądź w ramach oczekiwania na wyniki działań agentów pracujących w równoległych wątkach. Pod uwagę należy brać także formatowanie składni **markdown do HTML**, renderowanie LaTeX czy kodu, które przy strumieniowaniu mogą stanowić wyzwanie. Pojawiają się także biblioteki, takie jak [Streamdown](https://streamdown.ai/docs/getting-started) bądź [Markdown Parser](https://github.com/Simon-He95/markstream-vue/tree/main/packages/markdown-parser), które ułatwiają budowanie interfejsów po stronie front-endu. 

Poza renderowaniem bloków, AI może także generować interaktywne komponenty oraz wizualizacje, co powoli zaczyna być standaryzowane poprzez [MCP Apps](https://blog.modelcontextprotocol.io/posts/2025-11-21-mcp-apps/), [Apps SDK](https://developers.openai.com/apps-sdk) czy narzędzia takie jak [JSON Render](https://github.com/vercel-labs/json-render). Przechodzimy więc od interakcji opartych o tekst, do zaawansowanych interfejsów generowanych dynamicznie. 

![](https://cloud.overment.com/2026-01-17/ai_devs_4_ui-1da828db-5.png)

Zastosowaniem powyższych możliwości zajmiemy się niebawem. Tymczasem warto zapamiętać: **interakcja z agentami niemal zawsze będzie opierała się o zdarzenia**. Zyska to szczególną rolę, przy systemach wieloagentowych zdolnych do funkcjonowania w tle.
## Różnice pomiędzy interfejsem użytkownika, a logiką aplikacji
Treść generowana przez LLM zwykle ma formę tekstu. Dzięki jej strukturyzowaniu oraz połączeniu ze zdarzeniami, możemy prezentować ją w formie różnych, także interaktywnych interfejsów. Widzimy tutaj bardzo wyraźną różnicę pomiędzy tym, co generuje LLM, bieżącym stanem aplikacji oraz tym, co widzi użytkownik. 

Konkretnie:
- LLM generuje (zwykle) tekst w ustrukturyzowanej bądź nieustrukturyzowanej formie
- Aplikacja generuje dynamiczny interfejs, reaguje na zdarzenia (np. wywołanie narzędzi), kontroluje bieżący stan interfejsu (np. zgodę użytkownika na wykonanie akcji) oraz zarządza kontekstem konwersacji (np. przesyłając do modelu tylko część widocznych treści)
- Natomiast użytkownik widzi reprezentację bieżącego stanu aplikacji, która z technicznego punktu widzenia jest daleka od oryginalnej treści generowanej przez AI

Różnice między strukturą danych na back-endzie, a warstwą prezentacji są raczej normalne, ale obecność LLM jest czymś nowym, przez co łatwo popełnić błędy lub mocno utrudnić pracę. 

Gdy zaczynamy budować generatywne aplikacje, zwykle zaczynamy od przetwarzania wyłącznie tekstu, a sam interfejs jest bardzo prosty. Sugeruje to, że możemy po prostu przesyłać kolejne fragmenty generowane przez LLM i wyświetlać je użytkownikowi. To proste zapisywanie treści wiadomości asystenta, szybko okazuje się poważnym ograniczeniem szczególnie gdy aplikacja działa już na produkcji. 

![](https://cloud.overment.com/2026-01-17/ai_devs_4_events-b6a6066b-6.png)

Jakiekolwiek rozbudowanie interakcji staje się bardzo trudne, bo wymaga wprowadzenia zmian wszędzie, począwszy od bazy danych, przez logikę back-endu po front-end. A gdy z aplikacji korzystają już użytkownicy, musimy także migrować ich dane do nowych struktur. 

Znacznie lepszym pomysłem jest komunikacja oparta o semantyczne zdarzenia, które zawierają nie tylko sam tekst, ale także dodatkowe informacje (np. ID, typ bądź inne metadane) pozwalające na ich grupowanie czy rozbudowanie o właściwości wymagane po stronie interfejsu. Ich rozbudowa również zwykle nie stanowi większego problemu, bo polega wyłącznie na dodaniu nowych właściwości. 

![](https://cloud.overment.com/2026-01-17/ai_devs_4_semantic_events-0b1666d3-a.png)

Choć temat korzystania z narzędzi (Function Calling) jest jeszcze przed nami, to już teraz możemy przyjrzeć się przykładowej strukturze pokazującej, jak mogą wyglądać zdarzenia informujące o interakcji z otoczeniem. Widzimy tutaj, że ogólny schemat komunikacji pozostaje podobny, a zwykły tekst generowany przez LLM w formie semantycznych zdarzeń może być swobodnie prezentowany nawet w rozbudowanych i interaktywnych interfejsach.

![](https://cloud.overment.com/2026-01-17/ai_devs_4_semantic_tools-4f395589-2.png)

Powyższe wizualizacje jasno wskazują na ogromną rolę, jaką pełnią **semantyczne zdarzenia**. Zawierają one nie tylko podstawowe informacje zwracane przez model, lecz także dodatkowe właściwości dające nam kontrolę nad całą interakcją oraz sposobem generowania interfejsu. Oczywiście sama struktura obiektów reprezentujących te zdarzenia może się różnić w zależności od aplikacji, ale ogólne zasady pozostają takie same.
## Strategie wyboru dużych i mniejszych modeli w praktyce
Generatywne aplikacje zwykle korzystają z więcej niż jednego modeli. Jest to motywowane skutecznością, szybkością działania oraz ceną. W dodatku przy niektórych zadaniach nie będzie nam zależało na wyborze pomiędzy modelami, lecz zaangażowaniu kilku z nich. Problem w tym, że na pytanie **"jaki model jest najlepszy?"** nie ma odpowiedzi, ponieważ samo pytanie jest zadane błędnie i powinno być **"jaki model jest najlepszy w tej sytuacji?"**. Sugeruje to nam jasno, że jedynym sposobem wyboru modeli jest ich **sprawdzenie w praktyce**.

Przy wyborze modeli, warto zadbać o fundamenty w postaci systemu, który pozwoli pozostać nam na bieżąco z najnowszymi premierami i można to zrobić na przynajmniej kilka sposobów. Jednym z nich jest zaobserwowanie w mediach społecznościowych (szczególnie X oraz LinkedIn) kont firm: [OpenAI](https://openai.com/), [Anthropic](https://anthropic.com/), [DeepMind](https://deepmind.google/), [xAI](https://x.ai/) oraz w kontekście modeli otwartych [DeepSeek](https://www.deepseek.com/), [Z.ai](https://z.ai), [Qwen](https://qwen.ai/), [Bytedance](https://seed.bytedance.com/en/direction/llm), [Kimi](https://www.kimi.com/en), [Black Forest Labs](https://bfl.ai/), [Kling](https://klingai.com/global/) oraz oczywiście [Hugging Face](https://huggingface.co). Poza firmami warto obserwować także profile, newslettery oraz blogi ich pracowników, a także osoby które oni obserwują. Dobrym pomysłem jest dodanie do tej listy narzędzi (np. [LM Studio](lmstudio.ai)) oraz twórców narzędzi, które będziemy omawiać podczas AI_devs.

Innym sposobem na pozostawanie na bieżąco jest obserwowanie profili [OpenRouter](https://openrouter.ai/) czy [Replicate](https://replicate.com/), ponieważ niemal zawsze informują o najważniejszych premierach modeli. Nowe modele pojawiają się dość często i weryfikowanie skuteczności każdego z nich jest dość trudne. Na szczęście modele, które się wyróżniają, pojawiają się we wzmiankach Social Media znacznie częściej niż pozostałe, co może stanowić dla nas sygnał. 

Poza dostępem do informacji o pojawiających się modelach, dobrze jest stworzyć proces ich weryfikacji. Może on być bardzo indywidualny i opierać się o dowolny zestaw zadań, który odpowie na pytanie "czy ten model jest odpowiedni **dla mnie?**". Przykładowe zadania mogą obejmować:

- trudne wyzwania związane z problemami, które chcemy rozwiązać
- zadania związane z problemami, z którymi inne modele nie dają sobie rady
- zestawy zadań, które są dla nas ważne (np. już teraz adresują je nasze narzędzia)
- serie unikatowych łamigłówek weryfikujących różne zdolności modelu istotne dla nas
- zwykły "vibe check"

Można także zastosować podejście w pełni praktyczne, czyli przełączyć posiadane aplikacje na nowe modele i zaobserwować różnice w ich działaniu. Warto przy tym unikać ograniczania się wyłącznie do najpopularniejszych rozwiązań, ponieważ zamiast najnowszego modelu OpenAI można wykorzystać model Open Source, na przykład firmy z.ai, korzystając z platform takich jak OpenRouter.

Sam wybór modeli polega więc na sprawdzeniu skuteczności modelu na wybranych przez nas zadaniach. Proces ten można zautomatyzować poprzez narzędzia do ewaluacji generatywnych aplikacji, takich jak [Promptfoo](https://www.promptfoo.dev/)czy [DeepEval](https://deepeval.com/docs/getting-started), bądź po własnych skryptów. Temat ewaluacji będziemy omawiać jeszcze w dalszych lekcjach, więc na tym etapie wystarczy zadbać o wspomniane wyżej fundamenty oraz zastanowić się nad rodzajami zadań, które mogą być istotne w kontekście pojawiających się modeli. 

Zakładając, że posiadamy informacje o dostępnych na rynku modelach oraz orientujemy się w ich ogólnych umiejętnościach, możemy korzystać z kilku strategii wyboru modeli: 

1. **Główny model:** najprostsza konfiguracja w której cały system wykorzystuje jeden model
2. **Główny i Alternatywny:** najczęściej stosowany podział polega na wyborze pary dwóch modeli z których jeden jest możliwie najbardziej skuteczny (ale zwykle drogi i wolny), a drugi skupia się na szybkości i optymalizacji kosztowej. Wówczas ten "większy" model zajmuje się najtrudniejszymi zadaniami, a "mniejszy" pozostałymi.
3. **Główny i Specjalistyczne:** podobny do poprzedniej konfiguracji, jednak zamiast szybkości czy optymalizacji kosztowej priorytetem staje się skuteczność w wybranych zadaniach. Np. modele z.ai mogą sprawdzać się w generowaniu komponentów, modele Anthropic bądź Kimi w generowaniu treści tekstowych, a modele x.ai w szybkiej eksploracji systemu plików. 
4. **Zespół małych modeli:** dzięki niskim kosztom i szybkim działaniu możliwe jest zastosowanie wielu małych modeli oraz technik takich jak dekompozycja i głosowanie w celu uzyskania wysokiej skuteczności bez sięgania po najdroższe modele. Jest to jednak wymagające i rzadko spotykane podejście, szczególnie w ujęciu całych systemów, a nie pojedynczych zadań.

Stosowanie więcej niż jednego modelu niemal zawsze obejmuje pracę z więcej niż jednym providerem. Warto więc zadbać o to, aby aplikacja nie była ściśle powiązana wyłącznie z jednym z nich. Unikanie uzależnienia od jednego providera (tzw. vendor lock-in) jest także istotne ze względu na szybki rozwój modeli oraz zmiany "pozycji liderów".
## Najważniejsze natywne funkcjonalności API głównych providerów
Zanim przejdziemy dalej, zaznaczę, że pod pojęciem „głównych providerów” rozumiem firmy OpenAI, Anthropic, Gemini (DeepMind), xAI oraz platformę OpenRouter. Wybór ten podyktowany jest przede wszystkim jakością oferowanych przez nie modeli oraz ich dużą popularnością. 

Aktualnie trudno jest mówić o standardach API i każdy z providerów aktywnie je rozwija. Pomimo tego nawet własne integracje oparte o oficjalne SDK są relatywnie proste do ustawienia. Alternatywnie możemy sięgnąć po narzędzia takie jak [AI SDK](https://ai-sdk.dev/), aczkolwiek **stosowanie frameworków jest obecnie nierekomendowane**, ponieważ narzucają zbyt duże ograniczenia, nie oferując w zamian uzasadniającej tego wartości. Fakt, że w AI_devs nie będziemy z nimi pracować nie oznacza jednak, że nie można z nich korzystać. Tym bardziej, że wiedza z lekcji pozwoli znacznie lepiej zrozumieć mechaniki funkcjonujące u ich podstaw. 

Kluczowe funkcjonalności API, na które warto zwrócić uwagę to:

1. **Multimodalność:** generowanie i edycja obrazów, przetwarzanie audio czy wideo wciąż zarezerwowane są tylko dla wybranych providerów. Najlepszym wyborem jest tu [Interactions API](https://ai.google.dev/gemini-api/docs/interactions) od Gemini, a zaraz potem [Responses API](https://platform.openai.com/docs/api-reference/responses/create) OpenAI. Natomiast i tak najlepiej przygotować architekturę aplikacji tak, aby możliwe było korzystanie z innych providerów i modeli dla poszczególnych formatów.  
2. **Dostępność modeli:** poza generowaniem tekstu często istotne będą dla nas edycja i generowanie audio, obrazu i niekiedy także wideo oraz tzw. 'embedding'u'. W takich sytuacjach najlepiej wypadają API Gemini oraz OpenAI. Tym bardziej, że w ich przypadku do gry wchodzą także narzędzia dla interakcji w czasie rzeczywistym. 
3. **Natywne narzędzia:** web search, deep research, file search, computer use, code execution to popularne narzędzia natywnie dostępne w API. Ich skuteczność różni się pomiędzy providerami i nierzadko wiążą się ze znacznym uzależnieniem od danej platformy. W praktyce jednak, największym problemem zwykle są bardzo ograniczone możliwości konfiguracji i dopasowania. W zamian jednak są bardzo proste w użyciu.
4. **Cache:** to jeden z najważniejszych mechanizmów budowy agentów oraz interakcji z LLM działających na większej skali, którego rolą jest ograniczenie "przeliczania" danych wejściowych, przez co obniżony jest ich koszt oraz czas reakcji. Temat ten będziemy jeszcze omawiać, ale przy doborze providera warto zwrócić uwagę na dostępność tego mechanizmu. 
5. **Rate Limit:** po wyjściu z fazy developmentu limity API szybko stają się dużym wyzwaniem, szczególnie jeśli pracujemy na nowych kontach. Warto więc sprawdzić dostępne limity, wysłać zgłoszenie o ich zwiększenie bądź skorzystać z platform takich jak [OpenRouter](https://openrouter.ai/).

Providerzy oferują także API związane z funkcjonalnościami danej platformy, np. narzędzia do ewaluacji, fine-tuningu, vector store. W przeciwieństwie do narzędzi takich jak **web search**, tutaj pojawia się silne uzależnienie od danego dostawcy z którego na pewnym etapie dość trudno się uwolnić. 
## Najnowsze techniki organizowania instrukcji w kodzie aplikacji
Istnieje przynajmniej kilka sposobów na przechowywanie instrukcji (promptów) dostępnych w aplikacji. Wśród nich nie ma najlepszego i każdy ma swoje zalety w zależności od kontekstu. 

Są to przede wszystkim:

- Instrukcje "inline" występujące bezpośrednio w miejscu w którym dochodzi do wywołania modelu. Takie podejście sprawdza się do prostych zapytań, które nie zmieniają się zbyt często. 
- Instrukcje w oddzielnych plikach, zwykle umożliwiające tzw. **kompozycję promptu** wykorzystującą dynamiczne sekcje oraz zmienne. Jest to najbardziej popularne i zarazem elastyczne podejście. Wymaga jednak stosowania systemów do monitorowania interakcji z LLM w celu obserwowania finalnej treści promptu.
- Instrukcje w zewnętrznych systemach, np. [Langfuse](https://langfuse.com/), co umożliwia ich wersjonowanie, monitorowanie oraz zarządzanie poza kodem źródłowym aplikacji.
- Instrukcje zapisane w plikach markdown z ustawieniami w sekcji "frontmatter" w formacie yaml. Taka instrukcja dostępna jest z poziomu systemu plików także w czasie działania aplikacji, przez co prompty mogą być dynamicznie modyfikowane. Ten format szybko staje się pierwszym wyborem w przypadku systemów wieloagentowych.

Poszczególne strategie prezentują się następująco: 

![Techniki organizowania promptów w kodzie aplikacji](https://cloud.overment.com/2026-01-19/ai_devs_4_instructions-f2c596a2-1.png)

Naturalnie nic nie stoi na przeszkodzie, aby w jednej aplikacji korzystać z więcej niż jednego z tych podejść. Może się też zdarzyć, że kwestia promptów w ogóle zostanie pominięta ze względu na narzędzia takie jak [DSPy](https://dspy.ai/) czy [Ax](https://github.com/ax-llm/ax) w przypadku których posługujemy się sygnaturami (`input` → `output`) oraz modułami, które są automatycznie zamieniane na instrukcje dla modelu.

Jeśli mielibyśmy wybrać spośród powyższych technik tylko jedną, to zdecydowanie będą to prompty oparte o pliki markdown. Łączą one zalety niemal wszystkich pozostałych, posiadając przy tym unikatowe cechy związane z pełną dostępnością dla agentów AI w formie ich narzędzi. 

Wówczas interakcja może wyglądać tak jak poniżej, czyli: 

- Mamy *dwóch* agentów **Architect** oraz **Reporter**
- **Architect** może utworzyć nową umiejętność opisującą sposób generowania raportu oraz przypisać ją do agenta **Reporter**
- Następnie **Reporter** może wygenerować raport posługując się nową umiejętnością

![Dynamiczne generowanie nowych umiejętności dla agentów](https://cloud.overment.com/2026-01-19/ai_devs_4_dynamic-fb7254fd-5.png)

Powyższa interakcja jest też powszechnie spotykana w narzędziach CLI do kodowania, takich jak [Claude Code](https://code.claude.com/). Z powodzeniem sprawdzi się także w ramach tworzonych przez nas systemów agentowych i to nawet jeśli nie będzie nam zależało na możliwości dynamicznego generowania czy edycji promptów. 
## Generowanie instrukcji i techniki optymalizacji z pomocą LLM
Prompt Engineering powszechnie uznawany jest za niepotrzebną już umiejętność, ponieważ "AI wystarczająco dobrze rozumie polecenia użytkownika". W praktyce rzeczywiście z perspektywy użytkownika agentów takich jak [Cursor](https://cursor.com/) czy [Claude Code](https://code.claude.com/) możliwe jest prowadzenie naturalnej rozmowy i uzyskiwanie zadowalających rezultatów. Inaczej wygląda to z perspektywy **twórców** tych agentów.

Aby się o tym przekonać wystarczy spojrzeć na publikowane prompty systemowe narzędzi takich jak [Claude](https://code.claude.com/) czy [Grok](https://github.com/xai-org/grok-prompts/tree/main) oraz te będące wynikiem pracy osoby działającej pod nickiem [elder_plinus](https://github.com/elder-plinius/CL4R1T4S). W jego kontekście warto też zapoznać się z promptami wykorzystywanymi do tzw. jailbreakingu modeli, czyli procesu omijania ograniczeń narzucanych przez twórców. Można je zobaczyć [tutaj](https://github.com/elder-plinius/L1B3RT4S) (uwaga: korzystanie z tych promptów może doprowadzić do zawieszenia konta. Ich treść też niekiedy bywa wulgarna).  

Patrząc na jeden z promptów systemowych [Claude](https://claude.ai/) możemy wyróżnić szereg elementów, których obecność wpływa na doświadczenia użytkownika, a także ogólną jakość generowanych odpowiedzi. 

![Techniki stosowane w instrukcjach systemowych](https://cloud.overment.com/2026-01-19/ai_devs_4_prompt-3fcfeec3-1.png)

Wyróżniamy więc tutaj:

- **Strukturyzowanie** z pomocą tagów XML-like, które jasno sygnalizują początek oraz koniec danej sekcji. 
- **Tożsamość** której rolą jest nadanie ogólnego kontekstu interakcji oraz jej ogólnego zakresu, np. tematu rozmowy. Zatem nadanie roli w postaci "Johna Carmacka" (legendarny programista) nie sprawi magicznie, że model zyska znacznie lepsze umiejętności w programowaniu, ale nazwisko to skieruje jego uwagę w stronę skojarzeń związanych z programowaniem i postacią Johna. 
- **Limity** uwzględniane w instrukcji pozwalają na zmniejszenie ryzyka podjęcia działań przez model, których nie chcemy widzieć, np. zakaz poruszania określonych tematów. **Nie mamy jednak gwarancji**, że model zawsze będzie za nimi podążał, czego przykładem są prompty z profilu Elder Plinus.
- **Ograniczenia** dotyczące akcji, które model może realizować przy spełnieniu określonych warunków. Np. możliwość edycji wpisu na liście zadań musi być poprzedzona odnalezieniem go.
- **Styl** wypowiedzi, ton, format czy ogólna struktura mają wpływ zarówno na doświadczenie użytkownika, jak i działanie samego systemu. Przykładowo asystent komunikujący się **zwięźle** według określonych wytycznych będzie działał szybciej (choć z tym nie należy przesadzać ze względu na fakt, że "modele 'myślą' poprzez generowanie tokenów"). 
- **Bezpieczeństwo** dotyczy bezpośrednio świadomych działań użytkownika posiadającego złe intencje, np. dotyczące naruszenia zabezpieczeń interfejsu. Ponownie należy pamiętać, że instrukcje na poziomie promptu **można ominąć**, ale ich stosowanie jest wskazane ponieważ zmniejszają ryzyko niepożądanych zachowań. 
- **Adaptacja**, czyli instrukcje sygnalizujące modelowi oczekiwane zachowanie w sytuacji z którą naturalnie nie może sobie poradzić, np. ze względu na brak dostępu do potrzebnych informacji czy nieaktywne opcje interfejsu z którego korzysta użytkownik.
- **Kalibracja** obejmuje konkretne wskazówki dotyczące np. formatowania wypowiedzi w postaci chociażby prezentowania diagramów z wykorzystaniem składni [Mermaid](https://mermaid.js.org/). 

Kategorie powyżej są raczej **uniwersalne**, choć ich lista z pewnością nie jest kompletna. Wyraźnie rysują się tu jednak zestawy zasad, których celem jest stworzenie pewnego rodzaju przestrzeni w której model może się poruszać. Do pewnego stopnia przypomina to tworzenie sandboxów umożliwiających dość swobodne wykonywanie kodu, ale z uwzględnieniem określonych zasad. Ponownie jednak podkreślam, że w przypadku instrukcji systemowych **niemożliwe jest pełne zabezpieczenie się przed złośliwymi instrukcjami czy nieoczekiwanym zachowaniem modelu** i takie rzeczy musimy adresować na poziomie kodu oraz założeń projektowych. 

W przypadku agentów AI zdolnych do samodzielnego tworzenia instrukcji dla umiejętności czy nawet tworzenia innych agentów, ta "przestrzeń" o której mowa musi być jeszcze bardziej elastyczna i opierać się o zasady oraz schematy, na podstawie których AI samodzielnie będzie generować kolejne instrukcje. Coś takiego jest możliwe szczególnie teraz, gdy najnowsze modele zyskały bardzo dużą wiedzę na temat projektowania promptów czy nawet "samoświadomości" rozumianej jako posiadanie informacji na temat LLM oraz ich zachowań. Jednocześnie to, że jest "możliwe", nie oznacza, że jest oczywiste i **[SkillsBench](https://arxiv.org/abs/2602.12670)** sugeruje, że warto zachować tu ostrożność.
  
Projektowanie instrukcji dla modelu obejmuje także proces ich **debugowania** oraz **rozwoju**. Jednak w przeciwieństwie do kodu, nigdy nie wiemy dokładnie z czego wynika dane zachowanie lub w jaki sposób je wywołać. Jednocześnie mamy możliwość dodawania reguł oraz zasad, które **zwiększają prawdopodobieństwo** uzyskania pożądanych efektów, o czym możemy przekonać się jedynie obserwując zachowanie modelu. Jedną z najważniejszych zasad, którą dobrze jest się tutaj kierować jest coś, co można określić jako **generalizowanie generalizacji**. Innymi słowy nie chodzi o dodawanie specyficznych instrukcji, ani nawet ogólnych zasad, lecz kształtowanie promptu w taki sposób, aby **sterował "snem" modelu**. Temat ten będziemy poruszać wielokrotnie, ale już teraz można go zrozumieć przez poniższy przykład.

![Generalizowanie instrukcji/promptów przy kształtowaniu zachowań modelu](https://cloud.overment.com/2026-01-19/ai_devs_4_generalization-b9ae6fb2-a.png)

Widzimy tutaj sytuację w której model wyposażony w narzędzia **add_task** i **add_event** ma wyraźny problem z ich poprawnym wyborem na podstawie jedynie prostych instrukcji użytkownika. Błędne działanie początkowo zostaje zaadresowane poprzez **regułę bezpośrednio powiązaną** z pojawiającym się błędem, co sprawia, że model nie ma z nim już problemu. Jednak w ten sposób zaadresowaliśmy tylko jeden przykład i ewentualnie to, co model jest w stanie z niego wywnioskować. 

Znacznie lepszym rozwiązaniem okazuje się wówczas utworzenie reguł, które prowadzą model przez zgeneralizowany proces myślowy, który sprawdza się w przypadku niemal dowolnych zasad oraz konfiguracji narzędzi. W tym przypadku proces ten polega na **"głośnym" zastanowieniu się nad wyborem narzędzia, określeniu poziomu pewności oraz poproszeniu o doprecyzowanie w razie potrzeby**. Taka instrukcja nie jest bezpośrednio związana z błędem, lecz jego kategorią. Pomimo tego nie adresuje samej kategorii, lecz szeroki zbiór możliwych konfiguracji narzędzi oraz zadań. I to właśnie można nazwać "generalizowaniem generalizacji" (to nieoficjalny termin i raczej nie można go znaleźć w zewnętrznych źródłach).
## Specjalizowanie zachowania modeli poprzez kontekst, few-shot oraz many-shot
Modele językowe dysponują bazową wiedzą i umiejętnościami, które są wystarczające dla części zadań. Jednak projektowanie aplikacji w tym także agentów AI niemal zawsze będzie wymagało połączenia modelu z naszą własną bazą wiedzy oraz zestawem umiejętności, które wykraczają poza natywne możliwości modelu.

Nowa wiedza oraz kształtowanie umiejętności może odbywać się poprzez tzw. "in-context learning" czyli zdolność modeli językowych do zauważania wzorców w treści zapytania. W przypadku zewnętrznej wiedzy, niemal zawsze wystarczy aby po prostu znalazła się ona w kontekście zapytania, a model będzie w stanie z niej skorzystać przy generowaniu odpowiedzi. Jeśli jednak chcemy, aby model "nauczył się" sposobu wykonania zadania według ustalonych zasad, to wówczas dobrze jest nie tylko opisać te zasady, ale także zaprezentować na przykładach. Wówczas model wyraźnie rozpozna widoczne w nich wzorce i dość skutecznie będzie z nich korzystać.

Przykład promptu wykorzystującego przykłady few-shot widzimy poniżej. Instrukcja zawiera sekcję **examples** prezentującą przykładowe interakcje pomiędzy użytkownikiem, a modelem. Na ich podstawie możliwe jest rozpoznanie schematów rządzących klasyfikacją.

![Przykład promptu systemowego wykorzystującego few-shot](https://cloud.overment.com/2026-02-08/ai_devs_4_few-shot-cd5dd6a1-8.png)

Jeszcze do niedawna tworzyliśmy w tym celu sekcję w ramach instrukcji systemowej, np. `<context>` bądź `<examples>`. Obecnie jednak odbywa się to poprzez wyposażenie modelu w narzędzia umożliwiające wczytywanie treści zewnętrznych dokumentów, ale tylko wtedy, gdy jest to potrzebne. 

![](https://cloud.overment.com/2026-01-19/ai_devs_4_context-9e16c9f9-f.png)

Nie oznacza to jednak, że w instrukcji systemowej nie mogą znaleźć się treści sterujące zachowaniem modelu. Jednak ich charakter powinien być zdecydowanie bardziej zgeneralizowany aby z jednej strony dostarczyć istotne zasady interakcji z użytkownikiem, korzystania z narzędzi oraz eksploracji dostępnego kontekstu. Natomiast z drugiej strony instrukcja systemowa nie powinna zawierać szumu w postaci treści, które są zbędne przez większość czasu. 

Najnowsze LLMy świetnie wykorzystują treść dostępnego kontekstu, ale nie eliminuje to różnego rodzaju problemów wynikających z niewystarczającej wiedzy bądź błędnej formy jej prezentacji. 
## Structured Outputs w praktyce
Aby lepiej zrozumieć możliwości, które daje nam strukturyzowanie treści generowanych przez model, przyjrzymy się teraz bliżej narzędziu [01_01_grounding](https://github.com/i-am-alice/4th-devs/tree/main/01_01_grounding). Jego celem jest przetwarzanie plików tekstowych (np. Markdown) w taki sposób, aby LLM wybierał z treści **słowa kluczowe, definicje czy koncepcje**. Każda z wybranych fraz zostaje następnie przesłana do wyszukiwarki internetowej w celu uzyskania pogłębionego opisu. Uzyskane w ten sposób informacje trafiają do finalnej wersji dokumentu w którym słowa kluczowe są podświetlone, a po najechaniu na nie pojawia się tooltip.

Efekt jaki chcemy osiągnąć prezentuje poniższa wizualizacja. 

![Koncepcja narzędzia 'grounding'](https://cloud.overment.com/2026-01-20/ai_devs_4_hovers-31cb4284-3.png)

Aby zrealizować cel, tekst musi zostać przetworzony w kilku etapach:

- **Słowa kluczowe**: tekst musi zostać podzielony na sensowne fragmenty. W przypadku plików markdown zwykle będą to akapity. Dzięki temu bez względu na to jak długi będzie dokument, skrypt będzie mógł przetworzyć go fragmentami i wydobyć słowa kluczowe.
- **Połączenie duplikatów**: niektóre słowa kluczowe będą się powtarzać. LLM może jednak wskazać powiązania między nimi nawet wtedy, jeśli ich zapis będzie różnił się od siebie. Natomiast usunięcie duplikatów pozwoli uniknąć niepotrzebnych wyszukiwań.
- **Wyszukiwanie:** kolejny etap polega na przeszukaniu Internetu poprzez wykorzystanie natywnych narzędzi API OpenAI. W ten sposób pozyskujemy informacje na temat każdego z pobranych w pierwszym kroku definicji.
- **Generowanie dokumentu:** finalna wersja to dokument HTML utworzony na podstawie szablonu obsługującego mechaniki tooltipów oraz ogólne style. W ten sposób sama aplikacja skupia się jedynie na wygenerowaniu głównej treści. 

Powyższe kroki prezentują się następująco: 

![Etapy przetwarzania treści w Grounding Tool](https://cloud.overment.com/2026-01-20/ai_devs_4_grounding_pipeline-9f0f2680-a.png)

Każdy z nich następuje po sobie i wiąże się z wysłaniem serii zapytań w celu wygenerowania **ustrukturyzowanych danych**. W pierwszym kroku chodzi nam o słowa kluczowe, w drugim o ich aliasy, w trzecim o podsumowania, a w czwartym o fragmenty HTML. Od strony kodu potrzebujemy zatem:

- Prosty dostęp do systemu plików w celu odczytania i zapisania dokumentów
- Instrukcji / Promptu Systemowego dla każdego z etapów
- Schematów oczekiwanych odpowiedzi dla każdego z etapów
- Połączenia z LLM przez API z opcją udzielania odpowiedzi na podstawie wyników wyszukiwania

Struktura katalogów wygląda następująco: 

![](https://cloud.overment.com/2026-01-20/ai_devs_grounding_files-bba744dd-4.png)

**Ważne:** w niniejszej aplikacji dla nas istotne są jedynie **schematy JSON w katalogu "schema"** oraz **instrukcje w katalogu "prompts"**. Reszta logiki to jedynie detale implementacji, których nie ma potrzeby teraz eksplorować. Jednocześnie otworzenie kodu tego przykładu w Claude Code, Open Code bądź Cursor pozwoli na swobodne zadawanie pytań, co jest przydatne szczególnie jeśli nie pracujesz na co dzień w języku JavaScript.

W przykładzie `01_01_grounding` na uwagę zasługują przede wszystkim schematy. Ich struktura została wygenerowana przez AI, więc gdy będziesz tworzyć własne schematy, również skorzystaj z pomocy modelu. Jednocześnie warto jest upewnić się, że nazwy i opisy są wystarczająco precyzyjne i zgodne z naszymi oczekiwaniami. 

![](https://cloud.overment.com/2026-01-20/ai_devs_4_extract_schema-5f1c01f0-1.png)

Niezależnie od tego czy zapoznasz się z kodem tego narzędzia, czy nie, chciałbym zwrócić uwagę na kilka istotnych mechanizmów, które w nim są:

- Przetwarzanie tekstu opiera się o fragmenty nawet jeśli tekst w całości zmieści się do okna kontekstowego. Powodem jest **skupienie uwagi modelu** na mniejszym zakresie, przez co **skuteczność modelu jest wyższa**. Co więcej, otwiera mi to przestrzeń do zastosowania mniejszych, tańszych i szybszych modeli.
- Zapytania do LLM na poszczególnych etapach wysyłane są **równolegle** oraz w **grupach**. W ten sposób zmniejszam czas wykonania zadania, a jednocześnie unikam uderzenia w rate-limit API (limity mogą się pojawić na zupełnie nowych kontach).
- Postępy zapisywane są **w plikach tekstowych** (np. JSON), dzięki czemu możliwe jest wznowienie przetwarzania w przypadku błędu. 

Poniżej widzimy przykład działania narzędzia obejmujące **wykorzystanie pamięci podręcznej**. Po prostu gdy pliki dla danej notatki były już wygenerowane, nie ma potrzeby generować ich ponownie. 

![](https://cloud.overment.com/2026-01-20/ai_devs_4_grounding_cache-2132a9ea-d.png)

Efekt końcowy na przykładowej notatce można zobaczyć tutaj: [zobacz przykład](https://cloud.overment.com/ai_devs_4_grounding-1768942885.html). 

## Przykłady struktur baz danych dla czatbotów i agentów
Początkowo generatywne aplikacje miały charakter czatbotów, co wymagało przechowywania danych w prostej strukturze **konwersacji** oraz powiązanych z nimi **wiadomości**. Pozwalało to na budowanie interfejsów czatu oraz stosowaniu modeli do budowy automatyzacji czy wywołania w logice aplikacji.

![Schemat tabel 'conversations' i 'messages' dla prostego czatbota](https://cloud.overment.com/2026-01-19/ai_devs_4_structure-6162f68e-8.png)

Czatboty coraz częściej zastępowane są przez agentów AI zdolnych do niemal autonomicznego działania obejmującego interakcję z otoczeniem i przetwarzanie multimodalnych treści. Zwiększa się także horyzont czasowy oraz zakres i złożoność zadań, co przekłada się na potrzebę pracy asynchronicznej obejmującej system zdarzeń oraz zależności. Całość wymaga rozbudowanej komunikacji nie tylko z użytkownikiem, ale także pomiędzy agentami. Warto także rozważyć wdrożenie zaawansowanego monitorowania systemu, np. w postaci narzędzi takich jak [Langfuse](https://langfuse.com/) bądź dostępnych na rynku alternatyw.

Poniżej znajduje się **przykładowa struktura** bazy danych pochodząca z jednej z moich aplikacji. Interakcje z AI zorganizowane są w trzech tabelach:

- **sessions:** zawiera informacje o nazwie i statusie sesji powiązanej z użytkownikiem oraz agentem pełniącym rolę agenta nadrzędnego, koordynującego pracę pozostałych. 
- **agents:** to lista instancji agentów utworzonych w czasie sesji na podstawie predefiniowanych szablonów. Każdy agent posiada detale na temat swojego zadania, jego statusu i postępu realizacji. Istnieją tu też jasne powiązania z sesją, agentem zlecającym zadanie oraz konkretnym etapem jego pracy. 
- **items:** to lista poszczególnych etapów interakcji obejmująca treść wiadomości, wywołań narzędzi, a także załączniki w postaci obrazów i innych rodzajów dokumentów.

Taka struktura umożliwia współpracę całego zespołu agentów obejmującą dwukierunkową komunikację, w tym także kontakt z użytkownikiem, np. w celu zatwierdzenia wykonania akcji.

![Przykładowy schemat bazy danych dla systemu wieloagentowego](https://cloud.overment.com/2026-01-19/ai_devs_4_multiagent-e2eca7cf-8.png)

Przykładowa interakcja wykorzystująca omówiony schemat, obejmuje sesję w której użytkownik prosi o przygotowanie dziennego raportu na podstawie danych z aplikacji Linear. Agent o imieniu **Alice** zleca prośbę o jego przygotowanie do agenta **Claire** oraz zmienia swój status na "oczekujący". Następnie po otrzymaniu odpowiedzi samodzielnie wykorzystuje narzędzie do wysyłania maila, i zaraz po tym zwraca wiadomość potwierdzenia wykonanie zadania.

![Multi-agent Execution Flow / Interaction](https://cloud.overment.com/2026-01-19/ai_devs_4_multiagent-work-36a980ce-d.png)

Projektowanie struktur bazy danych będzie pojawiać się na przestrzeni całego szkolenia AI_devs, zatem będziemy mieć jeszcze wiele okazji na zrozumienie detali oraz eksplorację możliwych opcji. Jednocześnie już na tym etapie powyższe schematy powinny dać przynajmniej ogólny obraz rozwiązań, które będziemy budować. 
## Bieżący stan modeli open-source z LM Studio, ich możliwości oraz wymagania sprzętowe i przydatne opcje konfiguracji
Prawdopodobnie wiesz, że istnieje możliwość uruchomienia modeli językowych na własnym komputerze za pośrednictwem narzędzi takich jak [llama.cpp](https://github.com/ggml-org/llama.cpp), [mlx](https://github.com/ml-explore/mlx) czy [LM Studio](https://lmstudio.ai/) o ile tylko dysponujemy sprzętem który nam na to pozwala. Zazwyczaj modele open-source charakteryzuje jednak znacznie niższa skuteczność działania w porównaniu z komercyjnymi LLM. Jednocześnie wyspecjalizowane modele open source potrafią osiągać wyższą efektywność w niektórych zadaniach, zapewniając przy tym pełną prywatność. 

W praktyce jednak okazuje się, że większość firm decyduje się na pozostanie przy komercyjnych LLM albo poprzez API providerów z którymi będziemy pracować w AI_devs, albo usługi takie jak Amazon Bedrock czy Microsoft Azure. Natomiast inwestycja w sprzęt do lokalnej inferencji często okazuje się nieuzasadniona. 

Nie oznacza to jednak, że powinniśmy przechodzić obok otwartych modeli obojętnie, ponieważ jak wspomniałem zdarzają się sytuacje w których mogą się sprawdzić. Na początek wystarczy nam podstawowa wiedza na ich temat oraz przetestowanie działania kilku modeli z pomocą aplikacji [LM Studio](https://lmstudio.ai/). Po jej instalacji, wystarczy skorzystać z wyszukiwarki, aby odnaleźć modele takie jak:

- [Nemotron 3 Nano (macOS / Windows)](https://lmstudio.ai/models/nvidia/nemotron-3-nano)
- [GLM 4.7 Flash (macOS)](https://model.lmstudio.ai/download/mlx-community/GLM-4.7-Flash-4bit)
- [Qwen 3 Coder A3B (macOS)](https://model.lmstudio.ai/download/lmstudio-community/Qwen3-Coder-30B-A3B-Instruct-MLX-6bit)
- [Qwen 3 Coder A3B (Windows / macOS)](lmstudio-community/Qwen3-Coder-30B-A3B-Instruct-GGUF)

Na ich kartach powinny być widoczne informacje o tym, czy nasz system spełnia wymagania sprzętowe. Jeśli tak, możliwe będzie ich pobranie oraz uruchomienie i przetestowanie w interfejsie LM Studio. Warto poprowadzić z nimi dłuższą rozmowę wykraczającą poza kilka/kilkanaście wiadomości oraz zlecić kilka prostych zadań, np. programistycznych. W razie potrzeby można także aktywować lokalny serwer LM Studio i uzyskać dostęp do załadowanych modeli poprzez API o strukturze takiej samej jak OpenAI Chat Completion bądź [Responses API](https://lmstudio.ai/docs/developer/openai-compat/responses).

Istnieje także opcja sprawdzenia możliwości modeli lokalnych poprzez platformę [OpenRouter](https://openrouter.ai/). Tutaj sytuacja jest prostsza, bo wystarczy po zalogowaniu otworzyć czat i wybrać modele takie jak te wspomniane wyżej, bądź np. większe i znacznie lepsze alternatywy takie jak [GLM 4.7](https://openrouter.ai/z-ai/glm-4.7) czy [Minimax 2.1](https://openrouter.ai/minimax/minimax-m2.1). 

Tymczasem jest kilka aspektów na temat modeli Open Source, o których warto wiedzieć: 

- **Formaty (np. GGUF, MLX):** Określają strukturę pliku modelu i kompatybilność z narzędziami. GGUF działa z llama.cpp (macOS/Windows/Linux), MLX z Apple Silicon.
- **Liczba parametrów:** Ilość "wag" w sieci neuronowej (np. 7B, 70B). Więcej parametrów zwykle oznacza wyższą jakość, ale też wyższe wymagania sprzętowe i niższą szybkość generowania odpowiedzi (inferencji).
- **Poziom precyzji (kwantyzacji):** to kompresja wag wyrażona jako Q8, Q4 czy Q2, oznacza niższą precyzję przekładającą się na mniejszy rozmiar modelu i szybsze działanie, ale też niższą skuteczność. Poziom Q4/Q5 zwykle oznacza właściwy balans.
- **Okno kontekstu:** działa tak samo jak w przypadku modeli komercyjnych, jednak tutaj zauważymy także, że większe okno kontekstowe oznacza szybko rosnące zużycie pamięci. 
- **Wymagania sprzętowe:** kluczową rolę odgrywa ilość VRAM (GPU) lub Unified Memory (dla Apple Silicon), ponieważ model powinien być wczytany do pamięci w celu uzyskania najwyższej możliwej wydajności. Zwykle będziemy potrzebować od 32GB RAM w górę. Dla największych modeli konieczne jest posiadanie ~512GB RAM (np. Apple Mac Studio)

Do tematu modeli open-source będziemy jeszcze wracać. Powyższe informacje stanowią absolutne minimum i punkt startowy. 
## Aktualne źródła wiedzy, profile, narzędzia i usługi, które warto znać
Mówiąc o wyborze modeli wymieniałem profile firm oraz narzędzi, które warto obserwować, aby pozostawać na bieżąco w obszarze generatywnego AI. Poniżej znajduje się pełna lista:

- [Andrej Karpathy](https://x.com/karpathy): jeden ze współzałożycieli OpenAI
- [Demis Hassabis](https://x.com/demishassabis): CEO DeepMind
- [Dario Amodei](https://x.com/DarioAmodei): CEO Anthropic
- [Logan Kilpatrick](https://x.com/OfficialLoganK): product manager Google AI Studio
- [Omar Sanseviero](https://x.com/osanseviero): Developer Experience w Google DeepMind
- [Adam Goldberg](https://x.com/TheRealAdamG): GTM w OpenAI
- [Philipp Schmid](https://x.com/_philschmid): Developer Relations Google DeepMind
- [Alex Albert](https://x.com/alexalbert__): Developer Relations w Anthropic
- [Kent C Dodds](https://x.com/kentcdodds): autor szkoleń na temat Model Context Protocol
- [Clément Delangue](https://x.com/ClementDelangue): CEO Hugging Face
- [Teknium](https://x.com/Teknium): Co-founder NousResearch
- [Georgi Gerganov](https://x.com/ggerganov): twórca llama.cpp
- [Jerry Liu](https://x.com/jerryjliu0): twórca LlamaIndex 
- [Ivan Fioravant](https://x.com/ivanfioravanti): researcher działający głównie w obszarze modeli lokalnych / mlx
- [Awni Hannun](https://x.com/awnihannun): rozwija framework MLX w Apple
- [Prince Canuma](https://x.com/Prince_Canuma): rozwija narzędzia ekosystemu MLX
- [Pliny the Liberator](https://x.com/elder_plinius): researcher / red teaming 
- [David Shapiro](https://x.com/DaveShapi): researcher
- [AI Explained](https://www.youtube.com/@aiexplained-official): kanał YouTube na temat kluczowych wydarzeń w branży generatywnego AI
- [AI Engineer](https://www.youtube.com/@aiDotEngineer): kanał z wystąpieniami i warsztatami z obszaru generatywnego AI
- [Discover AI](https://www.youtube.com/@code4AI): kanał YouTube głównie na temat publikacji z obszaru generatywnego AI
- [Stanford Online](https://www.youtube.com/playlist?list=PLoROMvodv4rObv1FMizXqumgVVdzX4_05): kanał YouTube Uniwersytetu Stanford
- [Hugging Face](https://x.com/huggingface): społeczność i platforma dla AI / ML 
- [Google AI Developers](https://x.com/googleaidevs): społeczność Google dla developerów AI
- [Claude Code Community](https://x.com/claude_code): społeczność Claude Code
- [Cursor](https://x.com/cursor_ai): jeden z najbardziej popularnych edytorów AI
- [AI SDK](https://x.com/aisdk): profil AI SDK
- [OpenRouter](https://x.com/OpenRouterAI): platforma do inferencji większości dostępnych modeli językowych
- [Replicate](https://x.com/replicate): platforma do inferencji i fine-tuningu modeli image/video i innych
- [Stability AI](https://x.com/StabilityAI): twórcy modeli image / video 
- [Kling AI](https://klingai.com/global/): twórcy modeli image / video (Kling)
- [Unsloth](https://x.com/UnslothAI): platforma i narzędzia do fine-tuningu modeli AI
- [Promptfoo](https://x.com/promptfoo): narzędzie do ewaluacji promptów i agentów AI
- [Langfuse](https://x.com/langfuse): platforma do monitorowania generatywnych aplikacji
## Fabuła

[https://vimeo.com/1169554317](https://vimeo.com/1169554317)

## Transkrypcja filmu z Fabułą

"Numerze piąty! Znów się spotykamy. Wiem, że czytałeś mój list i wiesz, co stało się ze światem. Teraz wszystko, co nas otacza, jest kontrolowane przez "System"... yyy... czyli w sumie przez Zygfryda. Nie mam nawet pewności, że słowa, które do Ciebie teraz wypowiadam, nie są podsłuchiwane. System jest absolutnie wszędzie i kontroluje każdy aspekt ludzkiego życia. Każdą sekundę nagrania i każdą porcję informacji, która przesyłana jest przez sieć. System jest wszędzie.

Ale sam "System" nie jest zły, ale to, co dzieje się z systemem, jest złe. Odkąd Zygfryd przejął nad nim kontrolę, ludzie są zniewoleni. Musimy wspólnymi siłami doprowadzić świat do stabilizacji. Aż chciałoby się powiedzieć "musimy cofnąć czas" i w sumie nie byłoby w tym niczego nieprawdziwego, bo my naprawdę możemy to zrobić.

Pamiętasz co wydarzyło się w jaskini? Rafał... Andrzej... to od tego to się zaczęło. Rok temu zdobyłem dostęp do urządzenia umożliwiającego skoki w czasie. Mogę więc wrócić do tego momentu i sprawić, aby to co się stało, nigdy nie nastąpiło. Tylko...

W czasach, w których się znajdujemy, oficjalnie nie istnieje żadne źródło energii, które byłoby w stanie zasilić to urządzenie. W 2238 roku pewnie poszedłbym do sklepu i kupiłbym zwykłe baterie, ale ich moc porównywalna jest ze średniej wielkości elektrownią atomową z XXI wieku. Więc uwierz mi, nie jest to takie proste. Tutaj nie dostanę takich baterii. Szukałem nawet na Aliexpress. Nie mieli.

Nie będę roztaczał pod tą wizji, jak wiele kroków musimy wykonać, aby uratować świat. Skupmy się na tym, co jesteśmy w stanie zrobić tu i teraz. Potrzebujemy ENERGII i to jest fakt. Wraz ze specami z centrali wpadłem na pomysł jak rozwiązać ten problem.

Musimy uruchomić jedną z nieczynnych i niezarządzanych jeszcze przez "system" elektrowni atomowych. Gdy pozyskamy z niej energię, uruchomimy maszynę czasu, a wtedy już ja zajmę się resztą. Ale to nie jest takie proste. Uruchomienie elektrowni - zwłaszcza takiej, która nie działa od dziesiątek lat - to nie jest zwykłe użycie włącznika.

Słuchaj! Aby uruchomić elektrownie potrzebujemy specjalnego radioaktywnego paliwa. Jest ono cyklicznie transportowane pomiędzy elektrowniami. Przechwycimy jeden taki transport.

Na świecie żyje jeszcze garstka ludzi, których system wybrał, aby byli mu poddani. Wybierał ich na podstawie inteligencji, uległości, a także użyteczności w nowym, lepszym świecie. Mam dostęp do bazy danych osób, które przeżyły 'Wielką Korektę'.

Pomóż mi proszę wytypować osoby, które mogą być odpowiedzialne za organizację tych transportów. Więcej szczegółów znajdziesz w notatce dołączonej do tego filmu."

## Jak działają zadania w kursie

W trakcie kursu, pod lekcją w każdym dniu będzie pojawiać się jedno zadanie. Większość z nich wymaga wykonania kilku kroków i zgłoszenia poprawnej odpowiedzi do Centrali, czyli naszego hubu.

Hub ma swoją stronę internetową pod adresem: [https://hub.ag3nts.org/](https://hub.ag3nts.org/). Logowanie do hubu jest przez EasyCart, czyli system, w którym kupowaliście kurs. Na stronie hubu, w jego górnej części znajdziesz swój klucz API (więcej o nim poniżej). Jest tam też licznik punktów z zadań i punktów z zadań sekretnych. Poniżej znajduje się pole do wpisania zdobytych flag za zadania i sekrety. Plansza w głównej części strony pokazuje Twoje postępy. Pamiętaj, że do zdobycia certyfikatu wystarczy zdobycie 20 punktów z zadań podstawowych (sekrety nie liczą się do certyfikatu).

Jeśli chodzi o zdobywanie flag podczas rozwiązywania zadań, to zazwyczaj otrzymujesz je po wysłaniu poprawnej odpowiedzi do API hubu. Zgłoszenie odpowiedzi to wywołanie requestu POST z body w formacie JSON:

```json
{
  "apikey": "tutaj-twój-klucz-api",
  "task": "nazwa-zadania",
  "answer": "tutaj-odpowiedz-w-formie-wymaganej-przez-zadanie"
}
```

Hub odpowiada komunikatami o błędach lub informacją o zdobytej fladze. Flaga ma format `{FLG:....}`. Zdobytą w ten sposób flagę wpisujesz na stronie hubu i zdobywasz punkt. Flagę można wpisać zarówno w całości, jak i samą część po `FLG:`, czyli w przypadku kiedy otrzymasz `{FLG:PIZZA}`, w hubie możesz podać zarówno `{FLG:PIZZA}`, jak i `PIZZA`.

## Zadanie

Pobierz listę osób, które przeżyły 'Wielką Korektę' i które współpracują z systemem. Znajdziesz ją pod linkiem:
[https://hub.ag3nts.org/data/tutaj-twój-klucz/people.csv](https://hub.ag3nts.org/data/tutaj-tw%C3%B3j-klucz/people.csv)

Wiemy, że do organizacji transportów między elektrowniami angażowani są ludzie, którzy:

- są mężczyznami, którzy teraz w 2026 roku mają między 20, a 40 lat
- urodzonych w Grudziądzu
- pracują w branży transportowej

Każdą z potencjalnych osób musisz odpowiednio otagować. Mamy do dyspozycji następujące tagi:

- IT
- transport
- edukacja
- medycyna
- praca z ludźmi
- praca z pojazdami
- praca fizyczna

Jedna osoba może mieć wiele tagów. Nas interesują tylko ludzie pracujący w transporcie, którzy spełniają też poprzednie warunki.

Prześlij nam listę osób, którymi powinniśmy się zainteresować. Oczekujemy formatu odpowiedzi jak poniżej, wysłanego na adres https://hub.ag3nts.org/verify

Nazwa zadania to: **people**.

```json
{
       "apikey": "tutaj-twój-klucz-api",
       "task": "people",
       "answer": [
         {
           "name": "Jan",
           "surname": "Kowalski",
           "gender": "M",
           "born": 1987,
           "city": "Warszawa",
           "tags": ["tag1", "tag2"]
         },
         {
           "name": "Anna",
           "surname": "Nowak",
           "gender": "F",
           "born": 1993,
           "city": "Grudziądz",
           "tags": ["tagA", "tagB", "tagC"]
         }
       ]
     }
```

### Co należy zrobić w zadaniu?

1. **Pobierz dane z hubu** - plik `people.csv` dostępny pod linkiem z treści zadania (wstaw swój klucz API z https://hub.ag3nts.org/). Plik zawiera dane osobowe wraz z opisem stanowiska pracy (`job`).
2. **Przefiltruj dane** - zostaw wyłącznie osoby spełniające wszystkie kryteria: płeć, miejsce urodzenia, wiek.
3. **Otaguj zawody modelem językowym** - wyślij opisy stanowisk (`job`) do LLM i poproś o przypisanie tagów z listy dostępnej w zadaniu. Użyj mechanizmu Structured Output, aby wymusić odpowiedź modelu w określonym formacie JSON. Szczegóły we Wskazówkach.
4. **Wybierz odpowiednie osoby** - z otagowanych rekordów wybierz wyłącznie te z tagiem `transport`.
5. **Wyślij odpowiedź** - prześlij tablicę obiektów na adres `https://hub.ag3nts.org/verify` w formacie pokazanym powyżej (nazwa zadania: `people`).
6. **Zdobycie flagi** - jeśli wysłane dane będą poprawne, Hub w odpowiedzi odeśle flagę w formacie {FLG:JAKIES_SLOWO} - flagę należy wpisać pod adresem: https://hub.ag3nts.org/ (wejdź na tą stronę w swojej przeglądarce, zaloguj się kontem którym robiłeś zakup kursu i wpisz flagę w odpowiednie pole na stronie)

### Wskazówki

- **Structured Output - cel i sposób użycia:** Celem zadania jest zastosowanie mechanizmu Structured Output przy klasyfikacji zawodów przez LLM. Polega on na wymuszeniu odpowiedzi modelu w ściśle określonym formacie JSON przez przekazanie schematu (JSON Schema) w polu `response_format` wywołania API. Dokumentacja: [OpenAI](https://platform.openai.com/docs/guides/structured-outputs#supported-schemas), [Anthropic](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Gemini](https://ai.google.dev/gemini-api/docs/structured-output?example=recipe). Zadanie da się rozwiązać bez Structured Output, na przykład prosząc model o zwrócenie JSON-a i parsując go ręcznie - ale Structured Output eliminuje całą klasę błędów. Możesz też użyć bibliotek jak **Instructor** ([Python](https://python.useinstructor.com/)/[JS/TypeScript](https://js.useinstructor.com/)), które obsługują ten mechanizm za Ciebie.
- **Batch tagging - jedno wywołanie dla wielu rekordów:** Zamiast wywoływać LLM osobno dla każdej osoby, możesz na przykład wysłać w jednym żądaniu ponumerowaną listę opisów stanowisk i poprosić o zwrócenie listy obiektów z numerem rekordu i przypisanymi tagami. Znacznie zredukuje to liczbę wywołań API.
- **Opisy tagów pomagają modelowi:** Do każdej kategorii dołącz krótki opis zakresu - pomaga to modelowi poprawnie sklasyfikować niejednoznaczne stanowiska.
- **Format pól w odpowiedzi:** Pole `born` to liczba całkowita (sam rok urodzenia). Pole `tags` to tablica stringów, nie jeden string z przecinkami.

## Linki do filmu Mateusza

1. Przed wyruszeniem w drogę trzeba zebrać drużynę modeli [https://youtu.be/X2kWqlSnX1E?list=PL6gb3F2o2zOTJYxrcnWphmGLylXIlVCGJ](https://youtu.be/X2kWqlSnX1E?list=PL6gb3F2o2zOTJYxrcnWphmGLylXIlVCGJ), [https://arxiv.org/abs/2601.05106](https://arxiv.org/abs/2601.05106)
2. Współpraca między modelami [https://www.youtube.com/watch?v=DJI2XC71BlA&list=PL6gb3F2o2zOTJYxrcnWphmGLylXIlVCGJ&index=6](https://www.youtube.com/watch?v=DJI2XC71BlA&list=PL6gb3F2o2zOTJYxrcnWphmGLylXIlVCGJ&index=6), [https://arxiv.org/abs/2601.05167](https://www.youtube.com/redirect?event=video_description&redir_token=QUFFLUhqbVdUZWVFdU05aEU3aDhUX0RCUWtsUGhlT2xZUXxBQ3Jtc0trdmIzNGFPY1RnUjJOaUUyczNYOGtOODltNDNXNExqMlBfQzBmRlFlVXllbTd3VlpVWXVTTlJxdUg4UmtqcW1rQUxfQXBEczdxd3JRWkJoSDVjaE1Mdjk4R2Y0ZG5sUlpnRDhuSHp5Wlg2T0tiSUVENA&q=https%3A%2F%2Farxiv.org%2Fabs%2F2601.05167&v=DJI2XC71BlA)
