# Stripe 会员接入与本地测试

速下使用 **邮箱密码账号** + **Stripe Checkout 一次性 $9.90 USD** 开通永久 VIP。  
履约以 **Webhook** 为准；前端 success 回跳只负责刷新会员状态。

> Stripe API 调用走 `httpx`（项目已依赖），Webhook 按官方 HMAC 验签。密钥只放服务端 `.env`。

---

## 你需要准备什么

1. 注册 [Stripe Dashboard](https://dashboard.stripe.com/register)，打开右上角 **Test mode**。
2. **Developers → API keys** → 复制 **Secret key**（`sk_test_...`）。
3. （可选）**Product catalog** 新建商品「速下永久会员」、一次性价格 **$9.90 USD**，复制 `price_...`。  
   不配置 Price ID 时，后端会用 `price_data` 现场创建等价金额。
4. 安装 [Stripe CLI](https://stripe.com/docs/stripe-cli)，执行 `stripe login`。
5. 本机需能访问 `api.stripe.com`（国内通常开系统代理，例如 `127.0.0.1:7890`）。

---

## 配置 `.env`

复制 [`.env.example`](../.env.example) 为项目根目录 `.env`：

```env
SPEEDYDL_STRIPE_SECRET_KEY=sk_test_...
SPEEDYDL_STRIPE_WEBHOOK_SECRET=whsec_...
# SPEEDYDL_STRIPE_PRICE_ID=price_...
SPEEDYDL_PUBLIC_BASE_URL=http://127.0.0.1:5173
SPEEDYDL_API_PUBLIC_BASE_URL=http://127.0.0.1:8001
SPEEDYDL_ALLOW_DEMO_VIP=0
SPEEDYDL_AI_REQUIRE_VIP=1
```

`SPEEDYDL_STRIPE_WEBHOOK_SECRET`：本地用 CLI 打印的 `whsec_...`（见下），**不要**与 Dashboard 生产 Endpoint 的 secret 混用。

---

## 本地联调步骤（无公网域名）

终端 1 — 后端（可按需设置代理环境变量）：

```powershell
cd d:\luli
$env:HTTP_PROXY='http://127.0.0.1:7890'
$env:HTTPS_PROXY='http://127.0.0.1:7890'
$env:ALL_PROXY='http://127.0.0.1:7890'
.\.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

终端 2 — Stripe CLI 转发 Webhook：

```powershell
$env:HTTP_PROXY='http://127.0.0.1:7890'
$env:HTTPS_PROXY='http://127.0.0.1:7890'
stripe listen --forward-to localhost:8001/api/billing/webhook
```

注意路径必须是 **`/api/billing/webhook`（完整 webhook）**，少写字母会导致 404，支付成功也不会开通 VIP。

把 CLI 输出的 **webhook signing secret**（`whsec_...`）写入 `.env` 的 `SPEEDYDL_STRIPE_WEBHOOK_SECRET`，然后重启后端。

终端 3 — 前端：

```powershell
cd d:\luli\web
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`：

1. 点「开通会员」→ 注册 / 登录  
2. 「去支付 $9.90」→ 跳转 Stripe Checkout  
3. 测试卡：`4242 4242 4242 4242`，任意未来有效期、任意 CVC、任意邮编  
4. 支付成功回跳站点；CLI 应出现 `checkout.session.completed` → `200`  
5. 顶栏显示「永久会员」，可选 1080p+ / AI 总结  

取消支付应仍非 VIP。退出再登录 VIP 应仍在（SQLite `data/speedydl.db`）。

---

## 安全要点（已实现）

| 项 | 做法 |
|----|------|
| 验签 | Webhook 使用原始 body + `Stripe-Signature` HMAC |
| 幂等 | `stripe_events.event_id` 唯一；订单 `checkout_session_id` 唯一 |
| 防连点 | 创建 Session 带 `Idempotency-Key` |
| 履约 | `sessions.retrieve` 且 `payment_status=paid` 后才 `is_vip=true` |
| 密钥 | 仅服务端；不信任仅 success 回跳开通 |
| 已是会员 | `/api/billing/checkout` 直接拒绝，避免重复收款 |
| demo-vip | 默认关闭；仅 `SPEEDYDL_ALLOW_DEMO_VIP=1` 时可用 |

---

## 相关接口

见 [API.md](./API.md) 中 `/api/auth/*` 与 `/api/billing/*`。
