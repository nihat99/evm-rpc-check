# EVM RPC Check

A read-only Python CLI for checking an EVM endpoint against an expected chain ID
and block-zero hash. It can also check that a specific deployment address has
bytecode. It uses the Python 3.9+ standard library and requires no wallet or
third-party packages.

## Check GenLayer Bradbury Phase 3

```sh
python rpc_check.py --rpc https://rpc.testnet-chain.genlayer.com --chain-id 4221 --genesis 0x17d89764d4f4f963158fc4c5e8f2cb670c2837740b35f37081c12860c3df97e4 --contract 0x0192C6C9482251790965B7136352B26234d81d79
```

The expected values come from the [GenLayer network documentation](https://docs.genlayer.com/developers/networks).
Clarke and Bradbury Phase 3 share a chain ID and genesis. Use the documented
AddressManager address for the deployment you intend to use. The optional
`eth_getCode` check confirms that code exists at that address. Protocol
version, contract contents, and `gen_*` availability require separate checks.

For another EVM chain, supply the chain ID and genesis hash from its operator's
documentation. Omit `--contract` to check only the chain. The CLI prints JSON to
stdout when all checks pass and exits with status 1 and a diagnostic on stderr
when an endpoint check fails. Invalid CLI arguments exit with status 2.

For a health check, add `--max-head-age 120` to reject an endpoint whose latest
block is more than two minutes old. Choose a threshold that fits the chain's
block interval and keep the machine's clock synchronized. Successful checks
include the head's number, Unix timestamp, and age in seconds in the JSON output.

## Tests

```sh
python -m unittest -v
```

The tests use local response fixtures and make no network calls.
