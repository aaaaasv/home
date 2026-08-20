import html
import re

CODE_BLOCK_PATTERN = re.compile(r"```[^\n`]*\n?(.*?)```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")
HEADING_PATTERN = re.compile(r"^ {0,3}#{1,6}\s+(.+?)\s*#*$", re.MULTILINE)
ASTERISK_BOLD_PATTERN = re.compile(r"\*\*(\S.*?)\*\*", re.DOTALL)
UNDERSCORE_BOLD_PATTERN = re.compile(r"(?<![\w_])__(\S.*?)__(?![\w_])", re.DOTALL)
STRIKETHROUGH_PATTERN = re.compile(r"~~(\S.*?)~~", re.DOTALL)
BULLET_PATTERN = re.compile(r"^(\s*)[*+-][ \t]+", re.MULTILINE)
ASTERISK_ITALIC_PATTERN = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")
UNDERSCORE_ITALIC_PATTERN = re.compile(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])")
LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")

# \x00 cannot appear in a model answer and survives html escaping untouched
CODE_PLACEHOLDER = "\x00{index}\x00"


def render_markdown_as_html(text: str) -> str:
    """
    The model answers in markdown, telegram parses a small html subset — this converts one into the other. it also
    escapes the answer, so a stray "<" in the text can no longer make telegram reject the whole message
    """
    body, code_fragments = set_code_aside(text)
    body = html.escape(body)
    body = HEADING_PATTERN.sub(r"<b>\1</b>", body)
    body = ASTERISK_BOLD_PATTERN.sub(r"<b>\1</b>", body)
    body = UNDERSCORE_BOLD_PATTERN.sub(r"<b>\1</b>", body)
    body = STRIKETHROUGH_PATTERN.sub(r"<s>\1</s>", body)
    # bullets before italics, so a leading "* " is a bullet rather than the opening of an emphasis
    body = BULLET_PATTERN.sub(r"\1• ", body)
    body = ASTERISK_ITALIC_PATTERN.sub(r"<i>\1</i>", body)
    body = UNDERSCORE_ITALIC_PATTERN.sub(r"<i>\1</i>", body)
    body = LINK_PATTERN.sub(r'<a href="\2">\1</a>', body)
    return put_code_back(body.strip(), code_fragments)


def set_code_aside(text: str) -> tuple[str, list[str]]:
    """Code must reach telegram verbatim, so it is lifted out before the markdown rules run and put back after"""
    fragments: list[str] = []

    def lift(match: re.Match[str], tag: str) -> str:
        fragments.append(f"<{tag}>{html.escape(match.group(1))}</{tag}>")
        return CODE_PLACEHOLDER.format(index=len(fragments) - 1)

    lifted = CODE_BLOCK_PATTERN.sub(lambda match: lift(match, "pre"), text)
    return INLINE_CODE_PATTERN.sub(lambda match: lift(match, "code"), lifted), fragments


def put_code_back(text: str, fragments: list[str]) -> str:
    for index, fragment in enumerate(fragments):
        text = text.replace(CODE_PLACEHOLDER.format(index=index), fragment)
    return text
