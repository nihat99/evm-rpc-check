"""Check the chain identity of an EVM JSON-RPC endpoint."""

import argparse
import json
import math
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


QUANTITY = re.compile(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)")
BLOCK_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
BYTECODE = re.compile(r"0x(?:[0-9a-fA-F]{2})*")
MAX_RESPONSE_BYTES = 1_048_576


class CheckError(Exception):
    """The endpoint failed a transport, protocol, or identity check."""


def request_result(url, timeout, request_id, method, params):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    ).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"})

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise CheckError(f"{method}: HTTP {error.code}") from error
    except (URLError, OSError) as error:
        raise CheckError(f"{method}: could not read the endpoint response") from error

    if len(payload) > MAX_RESPONSE_BYTES:
        raise CheckError(f"{method}: response exceeds {MAX_RESPONSE_BYTES} bytes")
    try:
        result = json.loads(payload)
    except (UnicodeError, ValueError) as error:
        raise CheckError(f"{method}: invalid JSON response") from error

    if (
        not isinstance(result, dict)
        or result.get("jsonrpc") != "2.0"
        or type(result.get("id")) is not int
        or result["id"] != request_id
    ):
        raise CheckError(f"{method}: invalid JSON-RPC version or response ID")
    if "error" in result:
        error = result["error"]
        code = error.get("code") if isinstance(error, dict) else None
        if type(code) is int and "result" not in result:
            raise CheckError(f"{method}: JSON-RPC error {code}")
        raise CheckError(f"{method}: malformed JSON-RPC error response")
    if "result" not in result:
        raise CheckError(f"{method}: missing JSON-RPC result")
    return result["result"]


def check_endpoint(url, chain_id, genesis_hash, contract, timeout):
    value = request_result(url, timeout, 1, "eth_chainId", [])
    if not isinstance(value, str) or not QUANTITY.fullmatch(value):
        raise CheckError("eth_chainId: expected a hexadecimal JSON-RPC quantity")
    actual_chain_id = int(value, 16)
    if actual_chain_id != chain_id:
        raise CheckError(f"unexpected chain ID {actual_chain_id} (expected {chain_id})")

    genesis = request_result(url, timeout, 2, "eth_getBlockByNumber", ["0x0", False])
    block_hash = genesis.get("hash") if isinstance(genesis, dict) else None
    if (
        not isinstance(block_hash, str)
        or not BLOCK_HASH.fullmatch(block_hash)
        or genesis.get("number") != "0x0"
    ):
        raise CheckError("eth_getBlockByNumber: expected block zero and a 32-byte hash")
    if block_hash.lower() != genesis_hash.lower():
        raise CheckError(f"unexpected genesis hash {block_hash} (expected {genesis_hash})")

    report = {"chain_id": actual_chain_id, "genesis_hash": block_hash.lower()}
    if contract is not None:
        code = request_result(url, timeout, 3, "eth_getCode", [contract, "latest"])
        if not isinstance(code, str) or not BYTECODE.fullmatch(code):
            raise CheckError("eth_getCode: expected hexadecimal bytecode")
        if code == "0x":
            raise CheckError(f"no deployed bytecode at {contract}")
        report["contract"] = contract
        report["contract_code_bytes"] = (len(code) - 2) // 2
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", required=True, help="HTTP(S) JSON-RPC endpoint")
    parser.add_argument("--chain-id", required=True, type=int, help="expected decimal chain ID")
    parser.add_argument("--genesis", required=True, help="expected block-zero hash")
    parser.add_argument("--contract", help="optional address expected to have bytecode")
    parser.add_argument("--timeout", type=float, default=10, help="socket timeout in seconds")
    args = parser.parse_args(argv)

    try:
        url = urlsplit(args.rpc)
    except ValueError:
        parser.error("--rpc must be an HTTP(S) URL")
    if url.scheme not in {"http", "https"} or not url.hostname or url.username is not None:
        parser.error("--rpc must be an HTTP(S) URL without embedded credentials")
    if args.chain_id < 0:
        parser.error("--chain-id must be non-negative")
    if not BLOCK_HASH.fullmatch(args.genesis):
        parser.error("--genesis must be a 0x-prefixed 32-byte hash")
    if args.contract is not None and not ADDRESS.fullmatch(args.contract):
        parser.error("--contract must be a 0x-prefixed 20-byte address")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive number")

    try:
        result = check_endpoint(
            args.rpc, args.chain_id, args.genesis, args.contract, args.timeout
        )
    except CheckError as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
