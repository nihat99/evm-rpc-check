import io
import json
import unittest
from contextlib import redirect_stderr
from http.client import BadStatusLine
from urllib.error import URLError
from unittest.mock import patch

from rpc_check import CheckError, check_endpoint, main, request_result


URL = "https://rpc.example.invalid"
GENESIS = "0x" + "ab" * 32
CONTRACT = "0x" + "12" * 20


def response(request_id, result):
    return io.BytesIO(
        json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}).encode()
    )


class EndpointChecks(unittest.TestCase):
    @patch("rpc_check.urlopen")
    def test_reads_chain_genesis_and_deployment(self, urlopen):
        urlopen.side_effect = [
            response(1, "0x107d"),
            response(2, {"number": "0x0", "hash": GENESIS}),
            response(3, "0x6000"),
        ]
        self.assertEqual(
            check_endpoint(URL, 4221, GENESIS, CONTRACT, 5),
            {
                "chain_id": 4221,
                "genesis_hash": GENESIS,
                "contract": CONTRACT,
                "contract_code_bytes": 2,
            },
        )
        requests = [json.loads(call.args[0].data) for call in urlopen.call_args_list]
        self.assertEqual(
            [(item["method"], item["params"]) for item in requests],
            [
                ("eth_chainId", []),
                ("eth_getBlockByNumber", ["0x0", False]),
                ("eth_getCode", [CONTRACT, "latest"]),
            ],
        )
        self.assertTrue(all(call.kwargs == {"timeout": 5} for call in urlopen.call_args_list))

    @patch("rpc_check.urlopen")
    def test_rejects_wrong_chain_before_looking_up_genesis(self, urlopen):
        urlopen.return_value = response(1, "0x1")
        with self.assertRaisesRegex(CheckError, "unexpected chain ID 1"):
            check_endpoint(URL, 4221, GENESIS, None, 5)
        urlopen.assert_called_once()

    @patch("rpc_check.urlopen")
    def test_rejects_same_chain_id_with_different_genesis(self, urlopen):
        urlopen.side_effect = [
            response(1, "0x107d"),
            response(2, {"number": "0x0", "hash": "0x" + "00" * 32}),
        ]
        with self.assertRaisesRegex(CheckError, "unexpected genesis hash"):
            check_endpoint(URL, 4221, GENESIS, None, 5)

    @patch("rpc_check.urlopen")
    def test_rejects_address_without_bytecode(self, urlopen):
        urlopen.side_effect = [
            response(1, "0x107d"),
            response(2, {"number": "0x0", "hash": GENESIS}),
            response(3, "0x"),
        ]
        with self.assertRaisesRegex(CheckError, "no deployed bytecode"):
            check_endpoint(URL, 4221, GENESIS, CONTRACT, 5)

    @patch("rpc_check.urlopen")
    def test_rejects_noncanonical_chain_id(self, urlopen):
        urlopen.return_value = response(1, "0x0107d")
        with self.assertRaisesRegex(CheckError, "expected a hexadecimal"):
            check_endpoint(URL, 4221, GENESIS, None, 5)

    @patch("rpc_check.urlopen")
    def test_rejects_mismatched_response_id(self, urlopen):
        urlopen.return_value = response(2, "0x107d")
        with self.assertRaisesRegex(CheckError, "response ID"):
            request_result(URL, 5, 1, "eth_chainId", [])

    @patch("rpc_check.urlopen")
    def test_reports_rpc_error_code(self, urlopen):
        urlopen.return_value = io.BytesIO(
            b'{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"Method not found"}}'
        )
        with self.assertRaisesRegex(CheckError, "JSON-RPC error -32601"):
            request_result(URL, 5, 1, "eth_chainId", [])

    @patch("rpc_check.urlopen", side_effect=URLError("fixture timeout"))
    def test_reports_connection_failure(self, urlopen):
        with self.assertRaisesRegex(CheckError, "could not read"):
            request_result(URL, 5, 1, "eth_chainId", [])

    @patch("rpc_check.urlopen", side_effect=BadStatusLine("fixture invalid status line"))
    def test_reports_http_framing_failure(self, urlopen):
        with self.assertRaisesRegex(CheckError, "could not read the endpoint response"):
            request_result(URL, 5, 1, "eth_chainId", [])

    @patch("rpc_check.urlopen", side_effect=URLError("unexpected network request"))
    def test_rejects_invalid_rpc_ports_before_connecting(self, urlopen):
        for port in ("not-a-port", "65536", "0"):
            with self.subTest(port=port):
                args = [
                    "--rpc", f"https://rpc.example.invalid:{port}",
                    "--chain-id", "4221",
                    "--genesis", GENESIS,
                ]
                stderr = io.StringIO()
                with redirect_stderr(stderr), self.assertRaises(SystemExit) as exit_info:
                    main(args)
                self.assertEqual(exit_info.exception.code, 2)
                self.assertIn("--rpc", stderr.getvalue())
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
