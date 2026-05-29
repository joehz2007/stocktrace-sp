import re

_SEP = re.compile(r"[,，、;；\n\t]+")
_SUFFIXES = ["股份", "股票", "证券", "集团", "有限"]


class StockResolveError(Exception):
    pass


def split_inputs(text: str) -> list[str]:
    return [p.strip() for p in _SEP.split(text or "") if p.strip()]


def normalize_code(text: str) -> str | None:
    text = text.strip()
    if not text.isdigit():
        return None
    return text.zfill(6)


def resolve(token: str, search_fn) -> dict:
    token = token.strip()
    hits = search_fn(token)
    if hits:
        return {"code": hits[0]["code"], "name": hits[0]["name"]}
    code = normalize_code(token)
    if code:
        return {"code": code, "name": token if not token.isdigit() else code}
    for suf in _SUFFIXES:
        if token.endswith(suf):
            stripped = token[: -len(suf)]
            hits = search_fn(stripped)
            if hits:
                return {"code": hits[0]["code"], "name": hits[0]["name"]}
            break
    raise StockResolveError(f"无法匹配股票：{token}")
