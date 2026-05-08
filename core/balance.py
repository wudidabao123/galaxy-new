
# ── Model Balance ────────────────────────────────────

import os as _os

from data.model_store import get_model, get_model_api_key, list_models


def check_model_balance(model_id: str) -> dict:
    """Check API balance for a model (supports DeepSeek, OpenAI-compatible).
    Returns {"ok": bool, "balance": str, "currency": str, "error": str}."""
    import json, ssl
    from urllib.request import Request, urlopen
    
    model_info = get_model(model_id)
    if not model_info:
        return {"ok": False, "balance": "", "error": "Model not found"}
    
    api_key = get_model_api_key(model_id)
    if not api_key:
        return {"ok": False, "balance": "", "error": "No API key configured"}
    
    base_url = model_info.get("base_url", "")
    model_name = model_info.get("model", "")
    
    # DeepSeek balance endpoint
    if "deepseek" in base_url.lower():
        try:
            ctx = ssl.create_default_context()
            if _os.environ.get("GALAXY_SSL_VERIFY", "").lower() == "false":
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            
            req = Request(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            resp = urlopen(req, context=ctx, timeout=10)
            data = json.loads(resp.read().decode())
            
            if data.get("is_available", True):
                balance_infos = data.get("balance_infos", [])
                if balance_infos:
                    bi = balance_infos[0]
                    return {
                        "ok": True,
                        "balance": f"{float(bi.get('total_balance', 0)):.2f}",
                        "currency": bi.get("currency", "CNY"),
                        "topup_balance": f"{float(bi.get('total_topup_balance', 0)):.2f}",
                        "granted_balance": f"{float(bi.get('total_granted_balance', 0)):.2f}",
                        "error": "",
                    }
                return {"ok": True, "balance": "available", "currency": "?", "error": ""}
            else:
                return {"ok": False, "balance": "0", "error": "Account not available"}
        except Exception as e:
            return {"ok": False, "balance": "", "error": str(e)}
    
    # OpenAI balance check (billing)
    if "openai" in base_url.lower() or "api.openai" in base_url.lower():
        try:
            ctx = ssl.create_default_context()
            if _os.environ.get("GALAXY_SSL_VERIFY", "").lower() == "false":
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            
            # Check subscription
            req = Request(
                "https://api.openai.com/v1/dashboard/billing/subscription",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            resp = urlopen(req, context=ctx, timeout=10)
            data = json.loads(resp.read().decode())
            return {
                "ok": True,
                "balance": f"plan: {data.get('plan', {}).get('title', 'unknown')}",
                "currency": "USD",
                "error": "",
            }
        except Exception as e:
            # Try usage endpoint as fallback
            try:
                today = __import__('datetime').date.today().isoformat()
                req = Request(
                    f"https://api.openai.com/v1/usage?date={today}",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                resp = urlopen(req, context=ctx, timeout=10)
                return {
                    "ok": True,
                    "balance": "Usage data available",
                    "currency": "USD",
                    "error": "",
                }
            except:
                return {"ok": False, "balance": "", "error": str(e)}
    
    return {"ok": False, "balance": "", "error": f"Balance check not supported for {base_url}"}


def get_balance_for_all_models() -> list[dict]:
    """Check balance for all configured models."""
    import concurrent.futures
    models = list_models()
    results = []
    
    def check_one(m):
        mid = m["id"]
        b = check_model_balance(mid)
        return {"model_id": mid, "name": m["name"], "model": m.get("model", ""), **b}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(check_one, m) for m in models]
        for f in concurrent.futures.as_completed(futures, timeout=30):
            try:
                results.append(f.result(timeout=15))
            except Exception:
                pass
    
    return sorted(results, key=lambda r: r.get("name", ""))
