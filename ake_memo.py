"""A quiet, selectable Binance USDT-M perpetual ticker. No account or alerts."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import queue
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

SYMBOL = "AKEUSDT"
API = "https://fapi.binance.com"
FALLBACK_SYMBOLS = ("AKEUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
BASE = Path(__file__).resolve().parent
SETTINGS = BASE / "settings.json"
STATUS = BASE / "status.json"
KST = timezone(timedelta(hours=9))
POLL_SECONDS = 1


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def normalize_symbol(value):
    symbol = str(value).strip().upper().replace("/", "").replace(" ", "")
    if not symbol.endswith("USDT"):
        symbol += "USDT"
    if not re.fullmatch(r"\w{1,30}USDT", symbol):
        raise ValueError("Invalid USDT symbol")
    return symbol


def parse_quote(payload, symbol=SYMBOL):
    if not isinstance(payload, dict) or payload.get("symbol") != symbol:
        raise ValueError("Wrong market")
    try:
        price = Decimal(str(payload["lastPrice"]))
        change = Decimal(str(payload["priceChangePercent"]))
        stamp = int(payload["closeTime"]) / 1000
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("Incomplete quote") from exc
    if not price.is_finite() or price <= 0 or not change.is_finite() or not math.isfinite(stamp) or stamp <= 0:
        raise ValueError("Invalid quote")
    return {"symbol": symbol, "price": format(price, "f").rstrip("0").rstrip(".") if "." in format(price, "f") else format(price, "f"),
            "change_percent": f"{change:+.2f}%", "quote_time": stamp}


def request_json(path, limit=65536):
    request = Request(API + path, headers={"User-Agent": "Market-Memo/2.0", "Accept": "application/json"})
    with urlopen(request, timeout=6) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Unexpected response size")
    return json.loads(data)


def fetch_quote(symbol=SYMBOL):
    symbol = normalize_symbol(symbol)
    quote = parse_quote(request_json("/fapi/v1/ticker/24hr?" + urlencode({"symbol": symbol})), symbol)
    quote["received_at"] = time.time()
    return quote


def parse_symbols(payload):
    symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
    result = sorted({item["symbol"] for item in symbols if isinstance(item, dict)
                     and item.get("status") == "TRADING"
                     and item.get("contractType") in {"PERPETUAL", "TRADIFI_PERPETUAL"}
                     and item.get("quoteAsset") == "USDT" and isinstance(item.get("symbol"), str)
                     and re.fullmatch(r"\w{1,30}USDT", item["symbol"])})
    if not result:
        raise ValueError("No active USDT perpetual markets")
    return result


def fetch_symbols():
    return parse_symbols(request_json("/fapi/v1/exchangeInfo", limit=4 * 1024 * 1024))


def freshness(stamp, now=None):
    age = (time.time() if now is None else now) - stamp
    if age < -30:
        return "시각 확인 필요"
    if age > 60:
        return f"지연 {int(age)}초"
    return "연결됨"


def load_settings():
    try:
        value = json.loads(SETTINGS.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {}
        return value
    except (OSError, ValueError):
        return {}


class Memo:
    def __init__(self, root, start_worker=True):
        import tkinter as tk

        self.root = root
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.selection_lock = threading.Lock()
        self.messages = queue.Queue(maxsize=8)
        self.quote = None
        self.error = None
        self.settings = load_settings()
        try:
            self.symbol = normalize_symbol(self.settings.get("symbol", SYMBOL))
        except ValueError:
            self.symbol = SYMBOL
        self.generation = 0
        self.available_symbols = list(FALLBACK_SYMBOLS)
        self.catalog_loaded = False
        root.title("메모 · " + self.symbol.removesuffix("USDT"))
        root.configure(bg="#f7f7f4")
        root.minsize(266, 180)
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        default_x, default_y = max(0, screen_w - 310), 70
        try:
            x = max(0, min(int(self.settings.get("x", default_x)), max(0, screen_w - 286)))
            y = max(0, min(int(self.settings.get("y", default_y)), max(0, screen_h - 230)))
        except (ValueError, TypeError):
            x, y = default_x, default_y
        root.geometry(f"286x200+{x}+{y}")

        try:
            initial_opacity = max(35, min(100, int(self.settings.get("opacity", 100))))
        except (ValueError, TypeError):
            initial_opacity = 100
        self.opacity = tk.IntVar(root, initial_opacity)
        self.pinned = tk.BooleanVar(root, self.settings.get("pinned", True) is True)
        self.price_text = tk.StringVar(root, "—")
        self.change_text = tk.StringVar(root, "24시간 —")
        self.status_text = tk.StringVar(root, "연결 중 · Binance 선물")
        self.time_text = tk.StringVar(root, "시세 시각 —")

        frame = tk.Frame(root, bg="#f7f7f4", padx=14, pady=10)
        frame.pack(fill="both", expand=True)
        header = tk.Frame(frame, bg="#f7f7f4")
        header.pack(fill="x")
        from tkinter import ttk
        self.symbol_input = tk.StringVar(root, self.symbol)
        self.selector = ttk.Combobox(header, textvariable=self.symbol_input, values=self.available_symbols,
                                     width=13, font=("Segoe UI", 9))
        self.selector.pack(side="left", fill="x", expand=True)
        self.selector.bind("<KeyRelease>", self.filter_symbols)
        self.selector.bind("<<ComboboxSelected>>", self.select_symbol)
        self.selector.bind("<Return>", self.select_symbol)
        tk.Button(header, text="변경", command=self.select_symbol, font=("Malgun Gothic", 8),
                  bg="#f7f7f4", fg="#555750", bd=0, padx=3).pack(side="left", padx=(3, 0))
        tk.Checkbutton(header, text="고정", variable=self.pinned, command=self.set_pin,
                       font=("Malgun Gothic", 9), bg="#f7f7f4", fg="#666960",
                       activebackground="#f7f7f4", selectcolor="#f7f7f4", bd=0).pack(side="right")
        tk.Label(frame, textvariable=self.price_text, anchor="w", font=("Consolas", 25),
                 bg="#f7f7f4", fg="#30332d").pack(fill="x", pady=(4, 0))
        tk.Label(frame, textvariable=self.change_text, anchor="w", font=("Malgun Gothic", 9),
                 bg="#f7f7f4", fg="#555750").pack(fill="x")
        tk.Label(frame, textvariable=self.time_text, anchor="w", font=("Malgun Gothic", 8),
                 bg="#f7f7f4", fg="#777b72").pack(fill="x", pady=(5, 0))
        tk.Label(frame, textvariable=self.status_text, anchor="w", font=("Malgun Gothic", 8),
                 bg="#f7f7f4", fg="#777b72").pack(fill="x")
        controls = tk.Frame(frame, bg="#f7f7f4")
        controls.pack(fill="x", pady=(5, 0))
        self.opacity_text = tk.StringVar(root)
        tk.Label(controls, textvariable=self.opacity_text, font=("Malgun Gothic", 8),
                 bg="#f7f7f4", fg="#777b72").pack(side="left")
        tk.Scale(controls, from_=35, to=100, variable=self.opacity, orient="horizontal", showvalue=False,
                 command=self.set_opacity, bg="#f7f7f4", troughcolor="#dedfd9", highlightthickness=0,
                 bd=0, sliderlength=14, width=7).pack(side="right", fill="x", expand=True, padx=(6, 0))
        root.bind("<Escape>", lambda _event: root.iconify())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.set_pin()
        self.set_opacity()
        self.change_text.set("24시간 — · " + self.symbol)
        root.after(200, self.consume)
        root.after(1000, self.refresh_age)
        if start_worker:
            threading.Thread(target=self.worker, daemon=True, name="ake-public-quotes").start()
            threading.Thread(target=self.load_catalog, daemon=True, name="public-market-list").start()

    def filter_symbols(self, event=None):
        if event and event.keysym in ("Return", "Up", "Down", "Escape"):
            return
        needle = self.symbol_input.get().strip().upper().replace("/", "")
        self.selector.configure(values=[symbol for symbol in self.available_symbols if needle in symbol])

    def select_symbol(self, _event=None):
        try:
            symbol = normalize_symbol(self.symbol_input.get())
            if self.catalog_loaded and symbol not in self.available_symbols:
                raise ValueError("Inactive market")
        except ValueError:
            self.symbol_input.set(self.symbol)
            self.status_text.set("거래 중인 USDT 선물 종목을 선택하세요")
            return
        self.symbol_input.set(symbol)
        self.selector.configure(values=self.available_symbols)
        if symbol == self.symbol:
            return
        with self.selection_lock:
            self.symbol = symbol
            self.generation += 1
        self.quote = None
        self.error = None
        self.price_text.set("—")
        self.change_text.set("24시간 — · " + symbol)
        self.time_text.set("시세 시각 —")
        self.status_text.set("연결 중 · Binance 선물")
        self.root.title("메모 · " + symbol.removesuffix("USDT"))
        self.wake.set()
        self.save_settings()

    def load_catalog(self):
        try:
            self.messages.put_nowait({"symbols": fetch_symbols()})
        except Exception:
            # Manual entry and the last selected symbol remain usable offline.
            pass

    def set_pin(self):
        self.root.attributes("-topmost", bool(self.pinned.get()))

    def set_opacity(self, _value=None):
        value = self.opacity.get()
        self.root.attributes("-alpha", value / 100)
        self.opacity_text.set(f"불투명도 {value}%")

    def worker(self):
        failures = 0
        while not self.stop.is_set():
            started_at = time.monotonic()
            self.wake.clear()
            with self.selection_lock:
                symbol, generation = self.symbol, self.generation
            try:
                value = {"quote": fetch_quote(symbol)}
                failures = 0
            except Exception as exc:
                failures += 1
                reason = f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__
                value = {"error": reason}
            value.update(symbol=symbol, generation=generation)
            try:
                self.messages.put_nowait(value)
            except queue.Full:
                pass
            interval = POLL_SECONDS if failures == 0 else min(30, 5 * failures)
            self.wake.wait(max(0, interval - (time.monotonic() - started_at)))

    def apply_message(self, message):
        if "symbols" in message:
            self.available_symbols = message["symbols"]
            self.catalog_loaded = True
            self.filter_symbols()
            return
        # A slow response for the previous market must never replace the selected market.
        if message.get("generation") != self.generation or message.get("symbol") != self.symbol:
            return
        self.error = message.get("error")
        if "quote" in message:
            self.quote = message["quote"]
            self.price_text.set(self.quote["price"])
            self.change_text.set(f"24시간 {self.quote['change_percent']} · {self.symbol}")
            stamp = datetime.fromtimestamp(self.quote["quote_time"], KST)
            self.time_text.set(stamp.strftime("시세 %m/%d %H:%M:%S KST"))
        self.refresh_status()

    def consume(self):
        try:
            while True:
                message = self.messages.get_nowait()
                self.apply_message(message)
                self.write_status()
        except queue.Empty:
            pass
        if not self.stop.is_set():
            self.root.after(200, self.consume)

    def refresh_status(self):
        if self.error:
            self.status_text.set("연결 확인 필요 · 마지막 확인값" if self.quote else "시세 연결 불가 · 재시도 중")
        elif self.quote:
            self.status_text.set(f"{freshness(self.quote['quote_time'])} · Binance 선물")

    def refresh_age(self):
        self.refresh_status()
        if not self.stop.is_set():
            self.root.after(1000, self.refresh_age)

    def write_status(self):
        try:
            atomic_json(STATUS, {"pid": os.getpid(), "symbol": self.symbol, "market": "Binance USDT-M perpetual",
                                 "checked_at_kst": datetime.now(KST).isoformat(), "quote": self.quote,
                                 "error": self.error, "opacity": self.opacity.get(), "running": True})
        except OSError:
            pass

    def save_settings(self):
        try:
            atomic_json(SETTINGS, {"symbol": self.symbol, "opacity": self.opacity.get(), "pinned": self.pinned.get(),
                                   "x": self.root.winfo_x(), "y": self.root.winfo_y()})
        except OSError:
            pass

    def close(self):
        self.stop.set()
        self.wake.set()
        self.save_settings()
        try:
            atomic_json(STATUS, {"pid": os.getpid(), "running": False, "quote": self.quote})
        except OSError:
            pass
        self.root.destroy()


def self_test():
    sample = {"symbol": SYMBOL, "lastPrice": "0.00987200", "priceChangePercent": "-1.255", "closeTime": 1794898800000}
    result = parse_quote(sample)
    assert result["price"] == "0.009872"
    assert result["change_percent"] == "-1.26%"
    for changes in ({"symbol": "BTCUSDT"}, {"lastPrice": "NaN"}, {"lastPrice": "0"}, {"closeTime": "bad"}):
        try:
            parse_quote({**sample, **changes})
        except ValueError:
            continue
        raise AssertionError("Bad quote accepted")
    assert freshness(1000, 1005) == "연결됨"
    assert freshness(1000, 1070).startswith("지연")
    assert freshness(1100, 1000) == "시각 확인 필요"
    assert normalize_symbol(" btc/usdt ") == "BTCUSDT"
    assert normalize_symbol("eth") == "ETHUSDT"
    assert normalize_symbol("x") == "XUSDT"
    assert normalize_symbol("币安人生") == "币安人生USDT"
    for invalid in ("", "https://evil.invalid", "BTC?symbol=ETH"):
        try:
            normalize_symbol(invalid)
        except ValueError:
            continue
        raise AssertionError("Invalid symbol accepted")
    markets = [{"symbol": "BTCUSDT", "status": "TRADING", "contractType": "PERPETUAL", "quoteAsset": "USDT"},
               {"symbol": "ETHUSDT", "status": "SETTLING", "contractType": "PERPETUAL", "quoteAsset": "USDT"},
               {"symbol": "BTCUSDT_261225", "status": "TRADING", "contractType": "CURRENT_QUARTER", "quoteAsset": "USDT"},
               {"symbol": "SKHYUSDT", "status": "TRADING", "contractType": "TRADIFI_PERPETUAL", "quoteAsset": "USDT"},
               {"symbol": "SKHYNIXUSDT", "status": "SETTLING", "contractType": "TRADIFI_PERPETUAL", "quoteAsset": "USDT"},
               {"symbol": "OTHERUSDT", "status": "TRADING", "contractType": "TRADIFI_PERPETUAL", "quoteAsset": "USDC"}]
    assert parse_symbols({"symbols": markets}) == ["BTCUSDT", "SKHYUSDT"]
    print("PASS: quote validation, timestamps, symbol normalization, active perpetual filtering")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--list-symbols", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.check:
        print(json.dumps(fetch_quote(args.symbol), ensure_ascii=False, indent=2))
        return
    if args.list_symbols:
        symbols = fetch_symbols()
        print(json.dumps({"count": len(symbols), "sample": symbols[:10], "has_AKEUSDT": SYMBOL in symbols}, indent=2))
        return
    import tkinter as tk
    if args.smoke_test:
        root = tk.Tk()
        root.withdraw()
        memo = Memo(root, start_worker=False)
        root.update_idletasks()
        memo.opacity.set(55)
        memo.set_opacity()
        assert abs(root.attributes("-alpha") - .55) < .02
        memo.opacity.set(100)
        memo.set_opacity()
        assert abs(root.attributes("-alpha") - 1) < .02
        # Change markets without saving test preferences or mixing old responses.
        memo.save_settings = lambda: None
        memo.symbol_input.set("btc")
        memo.select_symbol()
        generation = memo.generation
        assert memo.symbol == "BTCUSDT" and memo.price_text.get() == "—"
        old = parse_quote({"symbol": SYMBOL, "lastPrice": "0.01", "priceChangePercent": "1", "closeTime": 1794898800000})
        memo.apply_message({"symbol": SYMBOL, "generation": generation - 1, "quote": old})
        assert memo.price_text.get() == "—"
        current = parse_quote({"symbol": "BTCUSDT", "lastPrice": "65000.12", "priceChangePercent": "2", "closeTime": 1794898800000}, "BTCUSDT")
        memo.apply_message({"symbol": "BTCUSDT", "generation": generation, "quote": current})
        assert memo.price_text.get() == "65000.12" and "BTCUSDT" in memo.change_text.get()
        memo.apply_message({"symbols": ["AKEUSDT", "BTCUSDT"]})
        memo.symbol_input.set("UNKNOWN")
        memo.select_symbol()
        assert memo.symbol == "BTCUSDT"
        root.destroy()
        print("PASS: window, opacity, switching, late-response isolation, inactive market rejection")
        return
    mutex = None
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        mutex = kernel32.CreateMutexW(None, False, "Local\\AkeMemoTickerV1")
        if not mutex:
            raise OSError("Unable to create application mutex")
        if ctypes.get_last_error() == 183:
            return
    root = tk.Tk()
    Memo(root)
    root.mainloop()
    if mutex:
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
