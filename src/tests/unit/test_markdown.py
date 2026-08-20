import unittest

from src.bot.markdown import render_markdown_as_html


class RenderMarkdownAsHtmlTestCase(unittest.TestCase):
    def test_render_markdown_as_html_converts_double_asterisks_to_bold(self):
        self.assertEqual(render_markdown_as_html("полий **сьогодні**"), "полий <b>сьогодні</b>")

    def test_render_markdown_as_html_converts_double_underscores_to_bold(self):
        self.assertEqual(render_markdown_as_html("полий __сьогодні__"), "полий <b>сьогодні</b>")

    def test_render_markdown_as_html_converts_single_asterisks_to_italic(self):
        self.assertEqual(render_markdown_as_html("це *приблизно*"), "це <i>приблизно</i>")

    def test_render_markdown_as_html_converts_single_underscores_to_italic(self):
        self.assertEqual(render_markdown_as_html("це _приблизно_"), "це <i>приблизно</i>")

    def test_render_markdown_as_html_leaves_underscores_inside_a_word_alone(self):
        self.assertEqual(render_markdown_as_html("змінна water_last_at у базі"), "змінна water_last_at у базі")

    def test_render_markdown_as_html_converts_a_heading_to_bold(self):
        self.assertEqual(render_markdown_as_html("## Полив\nраз на тиждень"), "<b>Полив</b>\nраз на тиждень")

    def test_render_markdown_as_html_converts_a_bullet_list_to_dots(self):
        self.assertEqual(render_markdown_as_html("- плющ\n* фікус\n  - непентес"), "• плющ\n• фікус\n  • непентес")

    def test_render_markdown_as_html_converts_a_bold_bullet_without_leaving_a_stray_asterisk(self):
        self.assertEqual(render_markdown_as_html("* **плющ** — раз на тиждень"), "• <b>плющ</b> — раз на тиждень")

    def test_render_markdown_as_html_converts_strikethrough(self):
        self.assertEqual(render_markdown_as_html("~~вчора~~ сьогодні"), "<s>вчора</s> сьогодні")

    def test_render_markdown_as_html_converts_a_link_to_an_anchor(self):
        self.assertEqual(
            render_markdown_as_html("див. [розклад](https://kyiv.ua/schedule)"),
            'див. <a href="https://kyiv.ua/schedule">розклад</a>',
        )

    def test_render_markdown_as_html_converts_inline_code(self):
        self.assertEqual(
            render_markdown_as_html("запусти `docker compose up`"), "запусти <code>docker compose up</code>"
        )

    def test_render_markdown_as_html_converts_a_fenced_block_to_preformatted_text(self):
        self.assertEqual(
            render_markdown_as_html("ось скрипт:\n```bash\nls -la\n```"), "ось скрипт:\n<pre>ls -la\n</pre>"
        )

    def test_render_markdown_as_html_keeps_markdown_inside_code_untouched(self):
        self.assertEqual(render_markdown_as_html("`a * b ** c_d`"), "<code>a * b ** c_d</code>")

    def test_render_markdown_as_html_escapes_angle_brackets_and_ampersands(self):
        self.assertEqual(
            render_markdown_as_html("вологість <40% & температура >25°"),
            "вологість &lt;40% &amp; температура &gt;25°",
        )

    def test_render_markdown_as_html_escapes_angle_brackets_inside_code(self):
        self.assertEqual(render_markdown_as_html("`<b>`"), "<code>&lt;b&gt;</code>")

    def test_render_markdown_as_html_leaves_plain_text_unchanged(self):
        self.assertEqual(render_markdown_as_html("Останній потяг о 22:45."), "Останній потяг о 22:45.")


if __name__ == "__main__":
    unittest.main()
