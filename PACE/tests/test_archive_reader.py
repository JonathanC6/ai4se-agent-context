import json
import io
import unittest
from unittest.mock import patch
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from benchmarks.archive_reader import ArchiveBrowser, archived, document


class ReaderTests(unittest.TestCase):
    def test_pdf_without_filename_extension_is_read_as_text(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=100)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page["/Resources"][NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 10 50 Td (Meeting program) Tj ET")
        page[NameObject("/Contents")] = stream
        buffer = io.BytesIO()
        writer.write(buffer)
        url = "https://example.org/download?id=123"
        with patch("benchmarks.archive_reader.download",
                   return_value=(buffer.getvalue(), url, "application/octet-stream", None)):
            _, fmt, text, _ = document(url, None)
        self.assertEqual(fmt, "pdf")
        self.assertIn("[p.1] Meeting program", text)

    def test_cdx_fallback_picks_capture_closest_to_request(self):
        url = "https://example.org/archive"
        records = [["timestamp","original"],["20240401120000",url],["20240514130000",url]]
        responses = [(b"{}", "", "", ""), (json.dumps(records).encode(), "", "", "")]
        with patch("benchmarks.archive_reader.download", side_effect=responses) as fetch:
            target = archived(url, "2024-05-15")
        self.assertIn("/cdx/search/cdx?", fetch.call_args.args[0])
        self.assertEqual(target, "https://web.archive.org/web/20240514130000id_/" + url)

    def test_snapshot_lookup_uses_requested_date_and_reports_capture(self):
        payload = {"archived_snapshots":{"closest":{"available":True,"status":"200","timestamp":"20240201120000"}}}
        url = "https://example.org/news?event=1"
        with patch("benchmarks.archive_reader.download", return_value=(json.dumps(payload).encode(), "", "", "")) as fetch:
            target = archived(url, "2024-02-02")
        self.assertIn("timestamp=20240202", fetch.call_args.args[0])
        self.assertEqual(target, "https://web.archive.org/web/20240201120000id_/" + url)

    def test_exposes_relative_document_links(self):
        url = "https://example.org/meeting/"
        html = b'<main><p>Schedule</p><a href="program.pdf">Program</a></main>'
        with patch("benchmarks.archive_reader.download", return_value=(html,url,"text/html","utf-8")):
            _, fmt, text, links = document(url, None)
        self.assertEqual(fmt,"html")
        self.assertIn("Schedule",text)
        self.assertEqual(links[url+"program.pdf"],"Program")

    def test_partial_failure_preserves_success_in_batch(self):
        from pathlib import Path
        browser = ArchiveBrowser(None, 0, Path("/nonexistent"))
        with patch.object(browser,"log"), patch("benchmarks.archive_reader.document",
                side_effect=[ValueError("missing"), ("https://example.org/b","pdf","[p.1] dates",{})]), \
                patch("benchmarks.archive_reader.extract_page", return_value="2024 dates"):
            results = json.loads(browser.visit({"url":["https://example.org/a","https://example.org/b"],"goal":"dates"}))
        self.assertEqual([r["read"] for r in results], [False,True])
        self.assertEqual(results[1]["format"],"pdf")
