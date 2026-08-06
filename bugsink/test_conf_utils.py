from unittest import TestCase

from .conf_utils import deduce_mcp_url, parse_database_url


class DeduceMcpUrlTestCase(TestCase):

    def test_no_proxy_uses_the_mcp_port_on_the_base_url_host(self):
        self.assertEqual("http://localhost:8100/mcp", deduce_mcp_url("http://localhost:8000", "", "8100"))

    def test_explicit_mcp_url_wins(self):
        self.assertEqual(
            "https://bugsink.example.com/mcp",
            deduce_mcp_url("https://bugsink.example.com", "https://bugsink.example.com/mcp", "8100"))

    def test_explicit_mcp_url_trailing_slash_is_normalized(self):
        self.assertEqual(
            "https://bugsink.example.com/mcp",
            deduce_mcp_url("https://bugsink.example.com", "https://bugsink.example.com/mcp/", "8100"))


class ParseDatabaseUrlTestCase(TestCase):

    def test_postgres_basic(self):
        result = parse_database_url("postgresql://user:secret@localhost/bugsink")
        self.assertEqual(result["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(result["USER"], "user")
        self.assertEqual(result["PASSWORD"], "secret")
        self.assertEqual(result["NAME"], "bugsink")
        self.assertEqual(result["HOST"], "localhost")
        self.assertEqual(result["PORT"], "5432")

    def test_postgres_scheme_alias(self):
        result = parse_database_url("postgres://user:secret@localhost/bugsink")
        self.assertEqual(result["ENGINE"], "django.db.backends.postgresql")

    def test_postgres_explicit_port(self):
        result = parse_database_url("postgresql://user:secret@db.example.com:5433/bugsink")
        self.assertEqual(result["HOST"], "db.example.com")
        self.assertEqual(result["PORT"], 5433)

    def test_postgres_percent_encoded_password(self):
        # @ and : in a password must be percent-encoded in the URL
        result = parse_database_url("postgresql://admin_usr_bugsink:p%40ss%3Aword@postgres.example.com:5432/bugsink")
        self.assertEqual(result["USER"], "admin_usr_bugsink")
        self.assertEqual(result["PASSWORD"], "p@ss:word")
        self.assertEqual(result["NAME"], "bugsink")

    def test_postgres_percent_encoded_username(self):
        result = parse_database_url("postgresql://u%2Bser:secret@localhost/bugsink")
        self.assertEqual(result["USER"], "u+ser")

    def test_postgres_double_encoded_percent(self):
        # %2525 in the URL -> %25 after one round of decoding -> the literal string %25
        result = parse_database_url("postgresql://user:p%2525word@localhost/bugsink")
        self.assertEqual(result["PASSWORD"], "p%25word")

    def test_postgres_percent_encoded_dbname(self):
        result = parse_database_url("postgresql://user:secret@localhost/bug%2Fsink")
        self.assertEqual(result["NAME"], "bug/sink")

    def test_postgres_no_credentials(self):
        result = parse_database_url("postgresql://localhost/bugsink")
        self.assertIsNone(result["USER"])
        self.assertIsNone(result["PASSWORD"])

    def test_mysql_basic(self):
        result = parse_database_url("mysql://user:secret@localhost/bugsink")
        self.assertEqual(result["ENGINE"], "django.db.backends.mysql")
        self.assertEqual(result["USER"], "user")
        self.assertEqual(result["PASSWORD"], "secret")
        self.assertEqual(result["NAME"], "bugsink")
        self.assertEqual(result["PORT"], "3306")

    def test_mysql_percent_encoded_password(self):
        result = parse_database_url("mysql://user:p%40ss%3Aword@localhost/bugsink")
        self.assertEqual(result["PASSWORD"], "p@ss:word")

    def test_mysql_percent_encoded_username(self):
        result = parse_database_url("mysql://u%2Bser:secret@localhost/bugsink")
        self.assertEqual(result["USER"], "u+ser")

    def test_mysql_percent_encoded_dbname(self):
        result = parse_database_url("mysql://user:secret@localhost/bug%2Fsink")
        self.assertEqual(result["NAME"], "bug/sink")

    def test_mysql_explicit_port(self):
        result = parse_database_url("mysql://user:secret@localhost:3307/bugsink")
        self.assertEqual(result["PORT"], 3307)

    def test_unsupported_scheme_raises(self):
        with self.assertRaises(ValueError) as cm:
            parse_database_url("sqlite:///path/to/db.sqlite3")
        self.assertIn("sqlite", str(cm.exception))
