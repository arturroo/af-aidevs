import frontmatter
import logging

logger = logging.getLogger("config")

def load_system_message(filepath: str = "system_message.md"):
    """
    Parses a markdown file with YAML frontmatter.
    Returns:
        tuple: (content_string, metadata_dict)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
        return post.content.strip(), post.metadata
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        return "You are a helpful assistant.", {}
