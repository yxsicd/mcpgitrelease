import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "deploy/git-credential-netrc"


class NetrcHelperTests(unittest.TestCase):
    def run_helper(self, host, content):
        with tempfile.TemporaryDirectory() as directory:
            netrc = pathlib.Path(directory) / "netrc"
            netrc.write_text(content, encoding="utf-8")
            env = os.environ.copy()
            env["NETRC"] = str(netrc)
            return subprocess.run(
                ["sh", str(HELPER), "get"],
                input=f"protocol=http\nhost={host}\n\n",
                text=True,
                capture_output=True,
                check=True,
                env=env,
            ).stdout

    def test_exact_host_match(self):
        output = self.run_helper(
            "git.example.test",
            "machine git.example.test\nlogin alice\npassword secret\n",
        )
        self.assertEqual(output, "username=alice\npassword=secret\n")

    def test_port_falls_back_to_netrc_hostname(self):
        output = self.run_helper(
            "git.example.test:3000",
            "machine git.example.test\nlogin alice\npassword secret\n",
        )
        self.assertEqual(output, "username=alice\npassword=secret\n")

    def test_unrelated_host_is_not_returned(self):
        output = self.run_helper(
            "other.example.test:3000",
            "machine git.example.test\nlogin alice\npassword secret\n",
        )
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
