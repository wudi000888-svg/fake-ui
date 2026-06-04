# Crypto Payments Design

## Goal

Add a self-hosted cryptocurrency payment module to fake-ui while keeping the existing frontend/backend split and the current order activation flow. Plans remain priced in USD. Users can pay with USDT, USDC, ETH, BNB, or BTC. Admins configure receiving addresses and chain endpoints. The panel verifies on-chain payment and automatically confirms the existing order after enough confirmations.

## Scope

| Included | Excluded |
|---|---|
| Admin-managed receiving addresses for Ethereum, BSC, and Bitcoin | Wallet private keys or signing |
| USD-priced orders with locked crypto amount at payment creation | Automatic refunds or payouts |
| USDT/USDC on Ethereum mainnet and BSC | Exchange custody or hosted payment gateways |
| ETH, BNB, and BTC payments | Full address scanning without a transaction id |
| User-submitted txid plus RPC/API verification | Secrets committed to Git |
| Manual admin refresh/retry controls | Direct production rollout before Singapore testing |

## Architecture

Use an independent payments module that links to the existing order module.

| Unit | Responsibility |
|---|---|
| `payments_store.py` | JSON persistence for payment methods, payment intents, rates, and verification history |
| `payment_rates.py` | Fetch and cache market rates; allow admin override rates |
| `payment_wallets.py` | Validate admin configured assets, chains, receiving addresses, confirmation counts, and endpoint URLs |
| `payment_verifier.py` | Verify EVM native transfers, EVM ERC20 transfers, and BTC transactions |
| `api_payment_routes.py` | Admin/user APIs for methods, payment creation, tx submission, and verification refresh |
| Frontend payment views | User payment page, QR display, tx submit form, admin payment configuration, admin order payment status |

Orders stay in `orders.json`. Payments live in `payments.json` and are linked by `order_id`. Existing order statuses remain `pending`, `completed`, and `cancelled`. Payment state is tracked separately.

## Data Model

`payments.json`:

| Field | Shape |
|---|---|
| `version` | `1` |
| `methods` | List of admin configured payment methods |
| `payments` | List of payment intents |
| `rates` | Cached rates and admin overrides |

Payment method fields:

| Field | Example | Notes |
|---|---|---|
| `id` | `usdt-eth-main` | Stable method id |
| `asset` | `USDT` | `USDT`, `USDC`, `ETH`, `BNB`, `BTC` |
| `chain` | `ethereum` | `ethereum`, `bsc`, `bitcoin` |
| `address` | `0x...` / `bc1...` | Receiving address only |
| `token_contract` | `0xdAC17F...` | ERC20/BEP20 only |
| `decimals` | `6` | Token/native decimals |
| `rpc_url` | `https://...` | EVM only |
| `btc_api_url` | `https://blockstream.info/api` | BTC only |
| `confirmations_required` | `12` | Admin configurable |
| `enabled` | `true` | Controls user visibility |

Payment intent fields:

| Field | Example |
|---|---|
| `id` | `pay_abcd1234` |
| `order_id` | `ord_abcd1234` |
| `username` | `alice` |
| `method_id` | `usdt-eth-main` |
| `asset` / `chain` | `USDT` / `ethereum` |
| `usd_amount` | `39.0` |
| `crypto_amount` | `39.000000` |
| `rate_usd` | `1.0` |
| `address` | Receiving address snapshot |
| `status` | `awaiting_payment`, `detected`, `confirmed`, `failed`, `expired` |
| `txid` | User-submitted transaction hash |
| `confirmations` | Latest confirmation count |
| `detected_amount` | Amount found on-chain |
| `expires_at` | Payment expiration timestamp |
| `created_at` / `updated_at` | ISO timestamps |
| `error` | Last verification error, sanitized |

## Payment Flow

| Step | Behavior |
|---|---|
| 1 | User creates an order from an enabled plan. The order stays `pending`. |
| 2 | User selects an enabled payment method. The backend creates a payment intent. |
| 3 | Backend locks USD amount, crypto amount, receiving address, exchange rate, and expiration. |
| 4 | Frontend shows QR code, address, exact amount, chain, and expiration. |
| 5 | User pays from their own wallet and submits txid. |
| 6 | Backend verifies txid through configured public RPC/API. |
| 7 | If amount, destination, asset, and confirmations match, payment becomes `confirmed`. |
| 8 | Backend calls the existing `user_admin.confirm_order(order_id)` path to open or renew service. |

The first implementation should not scan all chain history for an address. The primary supported path is txid submission plus automatic verification.

## Chain Verification

| Asset | Network | Verification |
|---|---|---|
| USDT | Ethereum | `eth_getTransactionReceipt`; parse ERC20 `Transfer(address,address,uint256)` logs for configured contract and receiving address |
| USDC | Ethereum | Same as USDT with USDC contract and decimals |
| USDT | BSC | Same ERC20/BEP20 log parsing through BSC RPC |
| USDC | BSC | Same ERC20/BEP20 log parsing through BSC RPC |
| ETH | Ethereum | `eth_getTransactionByHash`; check `to`, `value`; use current block number for confirmations |
| BNB | BSC | Same native transfer logic through BSC RPC |
| BTC | Bitcoin | Public API reads tx outputs, matching receiving address and amount; confirmations from tx status/block height |

Verification must reject:

| Case | Result |
|---|---|
| Wrong destination address | `failed` with a sanitized reason |
| Wrong token contract | `failed` |
| Amount below required amount after tolerance | `detected` or `failed`, depending on confirmations and amount |
| Not enough confirmations | `detected` |
| RPC/API unavailable | Keep previous status and record retryable error |
| Expired unpaid payment | `expired` |

## Rates

USDT and USDC default to `1 USD` with a configurable tolerance. ETH, BNB, and BTC use automatic public market rates with admin override.

| Behavior | Rule |
|---|---|
| Rate lock | Payment intent stores `rate_usd` and `crypto_amount` at creation |
| API failure | Use fresh cached rate if available; otherwise require admin override |
| Override | Admin can set per-asset USD price |
| Precision | Store crypto amount as decimal string, not binary float, in persisted payments |

## API Design

| Route | Role | Purpose |
|---|---|---|
| `GET /api/payment-methods` | user/admin | List enabled methods for users; all methods for admin |
| `POST /api/payment-methods/save` | admin | Create/update receiving address and RPC/API configuration |
| `POST /api/payment-methods/action` | admin | Enable/disable/delete methods |
| `POST /api/payments/create` | user/admin | Create payment intent for an existing pending order |
| `POST /api/payments/submit-tx` | user/admin | Attach txid and run verification |
| `POST /api/payments/refresh` | user/admin | Re-run verification for a payment |
| `GET /api/payments` | user/admin | List payment intents, scoped by role |
| `POST /api/payment-rates/save` | admin | Save admin override rates |

Existing `/api/orders/create` remains available. The frontend can create an order and then immediately create a payment intent.

## Frontend Design

| View | Changes |
|---|---|
| User plans/orders | Add a pay button for pending unpaid orders |
| Payment page | Show selected method, exact amount, address, QR code, expiration, txid form, and status |
| Admin orders | Show payment status, asset/chain, txid, confirmations, refresh button |
| Admin settings | Add payment methods table and form for receiving addresses and RPC/API endpoints |

The QR code should contain a wallet-friendly URI when possible:

| Asset | URI |
|---|---|
| BTC | `bitcoin:<address>?amount=<amount>` |
| ETH/BNB native | `ethereum:<address>?value=<amount>` for display convenience |
| USDT/USDC | Use address QR plus visible exact amount and token/network labels to avoid wallet incompatibility |

## Security

| Rule | Reason |
|---|---|
| Never store private keys | The panel only receives and verifies payment |
| Do not commit RPC keys or addresses unless sample-only | Avoid leaking production configuration |
| Sanitize RPC/API errors | Avoid exposing endpoint secrets |
| Persist only receiving addresses and public chain metadata | Limits blast radius |
| Require admin role for payment method configuration | Prevent address replacement attacks |
| Link payment intent to a single order and user | Prevent cross-order tx reuse |
| Reject txid already used by a confirmed payment | Prevent replay |

## Testing

| Test Area | Expected Coverage |
|---|---|
| Store | Method CRUD, payment creation, txid uniqueness, role-scoped listing |
| Rates | Override wins, cache fallback, amount lock precision |
| EVM parser | Native transfer, ERC20 Transfer log, wrong address, wrong contract, low amount |
| BTC parser | Output address match, amount match, confirmations |
| API | User creates payment only for own pending order; admin can configure methods |
| Order integration | Confirmed payment calls existing order confirmation and completes user activation |
| Frontend smoke | Payment method form, order pay button, txid submit, status rendering |

## Rollout

| Stage | Action |
|---|---|
| Local | Unit tests and API tests with mocked RPC/API responses |
| Singapore VPS | Deploy with test receiving addresses and public endpoints; create low-value test orders |
| Pre-production | Backup `data/` and verify rollback path |
| Hong Kong | Deploy only after Singapore passes payment creation, QR display, tx submit, verification, and auto-confirm |

## Open Decisions

| Decision | Selected |
|---|---|
| Main verification path | User submits txid; backend verifies through RPC/API |
| Pricing currency | USD |
| EVM chains | Ethereum mainnet and BSC |
| BTC verification | Public API allowed |
| Wallet custody | No private keys, receive-only |
