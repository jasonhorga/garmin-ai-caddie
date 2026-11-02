from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HARNESS = r'''
require "json"

module UI
  class << self
    attr_accessor :failures
    def user_error!(message)
      raise "USER_ERROR: #{message}"
    end
    def message(*) end
    def important(message)
      failures << message
    end
  end
end

def default_platform(*) end
def platform(*)
  yield
end
def desc(*) end
def lane(*) end

load ARGV.fetch(0)

module Process
  class << self
    attr_accessor :now
    def clock_gettime(*)
      now
    end
  end
end
module Kernel
  def sleep(seconds)
    $sleeps << seconds
    Process.now += seconds
  end
end

class FakeHttp
  attr_accessor :use_ssl, :open_timeout, :read_timeout
  def request(request)
    raise "missing JSON accept" unless request["Accept"] == "application/json"
    raise "missing admin token" unless request["X-AI-Caddie-Admin-Token"] == "fixture-token"
    if request.path == "/api/v2/readiness"
      $readiness_requests += 1
      body = {"schema" => "ai-caddie-readiness-v1", "authenticated" => true,
              "status" => "ready", "runtimeStatus" => "ready", "serviceStatus" => "ready",
              "checks" => [{"label" => "history", "state" => "ready"}]}
      return Struct.new(:code, :body).new("200", JSON.generate(body))
    end
    raise "unexpected path" unless request.path == "/api/v2/health"
    raise "changed health timeouts" unless open_timeout == 20 && read_timeout == 20
    $health_requests += 1
    event = $events.length > 1 ? $events.shift : $events.first
    # Include a deterministic per-request duration in the logged elapsed time.
    Process.now += 0.125
    if event["error"]
      klass = event["error"].split("::").inject(Object) { |scope, name| scope.const_get(name) }
      raise klass, "fixture connection failure"
    end
    Struct.new(:code, :body).new(event.fetch("code", "200"), event.fetch("body"))
  end
end
class << Net::HTTP
  def new(*)
    FakeHttp.new
  end
end

ENV["AI_CADDIE_API_BASE_URL"] = "https://api.example.test"
ENV["AI_CADDIE_ADMIN_TOKEN"] = "fixture-token"
ENV["EXPECTED_BACKEND_REVISION"] = "a" * 40

JSON.parse(STDIN.read).each do |config|
  Process.now = 0.0
  UI.failures = []
  $sleeps = []
  $health_requests = 0
  $readiness_requests = 0
  $events = config.fetch("events")
  begin
    value = if config.fetch("entry") == "preflight"
      preflight_backend!.fetch("revision")
    else
      backend_revision!(expected: "a" * 40)
    end
    result = {"result" => "pass", "revision" => value}
  rescue => error
    result = {"result" => "error", "error_class" => error.class.to_s, "message" => error.message}
  end
  puts JSON.generate(result.merge("requests" => $health_requests, "sleeps" => $sleeps,
                                  "logs" => UI.failures, "readiness_requests" => $readiness_requests))
end
'''


class FastfileHealthRetryTests(unittest.TestCase):
    """G7: TestFlight health/revision gates; retry limits come from the C314 card."""

    def run_cases(self, cases: list[dict]) -> list[dict]:
        ruby = shutil.which("ruby")
        if ruby is None:
            self.skipTest("ruby is not installed locally; Fastfile behavior needs Ruby")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = root / "spaceship" / "connect_api.rb"
            stub.parent.mkdir()
            stub.write_text("module Spaceship; module ConnectAPI; end; end\n", encoding="utf-8")
            script = root / "harness.rb"
            script.write_text(HARNESS, encoding="utf-8")
            result = subprocess.run(
                [ruby, str(script), str(Path("fastlane/Fastfile").resolve())],
                input=json.dumps(cases), env={**os.environ, "RUBYLIB": str(root)},
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows), len(cases), result.stdout)
        return rows

    @staticmethod
    def health(**overrides) -> dict:
        return {"body": json.dumps({"schema": "ai-caddie-health-v2", "revision": "a" * 40, **overrides})}

    def test_G7_health_connection_failure_then_success(self) -> None:
        """Both gates tolerate one failed connection and log its attempt and duration."""
        errors = ["Net::OpenTimeout", "Net::ReadTimeout", "Errno::ECONNRESET",
                  "Errno::ECONNREFUSED", "EOFError", "OpenSSL::SSL::SSLError", "SocketError"]
        cases = [{"entry": entry, "events": [{"error": error}, self.health()]}
                 for entry in ("preflight", "revision") for error in errors]
        for case, row in zip(cases, self.run_cases(cases)):
            with self.subTest(entry=case["entry"], error=case["events"][0]["error"]):
                self.assertEqual(row["result"], "pass", row)
                self.assertEqual(row["revision"], "a" * 40)
                self.assertEqual(row["requests"], 2, row)
                self.assertEqual(row["sleeps"], [5], row)
                self.assertEqual(row["readiness_requests"], 1 if case["entry"] == "preflight" else 0)
                self.assertEqual(len(row["logs"]), 1, row)
                self.assertIn("attempt 1", row["logs"][0])
                self.assertIn("elapsed_ms=125.0", row["logs"][0])
                self.assertIn("error=" + case["events"][0]["error"], row["logs"][0])

    def test_G7_health_persistent_timeout_stops_after_three_attempts(self) -> None:
        cases = [{"entry": entry, "events": [{"error": "Net::OpenTimeout"}]}
                 for entry in ("preflight", "revision")]
        for case, row in zip(cases, self.run_cases(cases)):
            with self.subTest(entry=case["entry"]):
                self.assertEqual(row["result"], "error", row)
                self.assertEqual(row["error_class"], "Net::OpenTimeout", row)
                # Card: three total attempts; only two waits, 5 s then 15 s.
                self.assertEqual(row["requests"], 3, row)
                self.assertEqual(row["sleeps"], [5, 15], row)
                self.assertEqual(len(row["logs"]), 3, row)
                for attempt, log in enumerate(row["logs"], 1):
                    self.assertIn(f"attempt {attempt}", log)
                    self.assertIn("elapsed_ms=125.0", log)
                    self.assertIn("error=Net::OpenTimeout", log)

    def test_G7_health_server_errors_retry_through_third_attempt(self) -> None:
        cases = [{"entry": entry, "events": [{"code": "500", "body": "unavailable"},
                                              {"code": "503", "body": "unavailable"}, self.health()]}
                 for entry in ("preflight", "revision")]
        for case, row in zip(cases, self.run_cases(cases)):
            with self.subTest(entry=case["entry"]):
                self.assertEqual(row["result"], "pass", row)
                self.assertEqual(row["requests"], 3, row)
                self.assertEqual(row["sleeps"], [5, 15], row)
                self.assertEqual(len(row["logs"]), 2, row)
                for log in row["logs"]:
                    self.assertIn("error=BackendRetryableError", log)

    def test_G7_health_non_200_client_and_redirect_responses_fail_immediately(self) -> None:
        cases = [{"entry": entry, "events": [{"code": code, **self.health()}, self.health()]}
                 for entry in ("preflight", "revision") for code in ("403", "404", "301", "204")]
        for case, row in zip(cases, self.run_cases(cases)):
            with self.subTest(entry=case["entry"], code=case["events"][0]["code"]):
                self.assertEqual(row["result"], "error", row)
                self.assertIn("HTTP " + case["events"][0]["code"], row["message"])
                self.assertEqual(row["requests"], 1, row)
                self.assertEqual(row["sleeps"], [], row)

    def test_G7_health_invalid_evidence_fails_immediately(self) -> None:
        invalid = [(self.health(revision="b" * 40), "revision"),
                   ({"body": json.dumps({"schema": "ai-caddie-health-v2"})}, "revision"),
                   (self.health(revision="invalid"), "revision"),
                   (self.health(schema="wrong"), "schema"),
                   ({"body": "not JSON"}, None)]
        cases = [{"entry": entry, "events": [event, self.health()]}
                 for entry in ("preflight", "revision") for event, _ in invalid]
        messages = [message for _ in ("preflight", "revision") for _, message in invalid]
        for case, message, row in zip(cases, messages, self.run_cases(cases)):
            with self.subTest(entry=case["entry"], evidence=case["events"][0]):
                self.assertEqual(row["result"], "error", row)
                if message:
                    self.assertIn(message, row["message"])
                elif case["entry"] == "revision":
                    self.assertIn("response is invalid", row["message"])
                else:
                    self.assertEqual(row["error_class"], "JSON::ParserError", row)
                self.assertEqual(row["requests"], 1, row)
                self.assertEqual(row["sleeps"], [], row)


if __name__ == "__main__":
    unittest.main()
