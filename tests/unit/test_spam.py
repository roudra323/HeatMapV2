from decimal import Decimal

from heatmap_core.config.settings import SpamConfig
from heatmap_core.normalize.spam import (
    TokenInfo,
    TransferInfo,
    lookalike,
    token_spam_reason,
    transfer_spam_reasons,
)
from tests.support import addr

USDT = addr(0xA1)
VERIFIED = {"USDT": USDT, "ETH": "0x" + "e" * 40}
CONFIG = SpamConfig(airdrop_min_recipients=3)


def token(
    symbol: str, name: str = "x", address: str = addr(0xBAD), verified: bool = False
) -> TokenInfo:
    return TokenInfo(address=address, symbol=symbol, name=name, is_verified=verified)


def test_token_rules() -> None:
    assert token_spam_reason(token("USDТ"), VERIFIED, CONFIG) == "non_ascii_symbol"
    assert token_spam_reason(token("ꓴꓢꓓꓔ"), VERIFIED, CONFIG) == "non_ascii_symbol"
    assert (
        token_spam_reason(token("GIFT", "Visit usdt-claim.com"), VERIFIED, CONFIG) == "promo_text"
    )
    assert token_spam_reason(token("usdt"), VERIFIED, CONFIG) == "impersonates:USDT"
    assert token_spam_reason(token("USDT", address=USDT, verified=True), VERIFIED, CONFIG) is None
    assert token_spam_reason(token("FOO", "Foo Token"), VERIFIED, CONFIG) is None


def test_lookalike() -> None:
    real = "0x1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa5678"
    fake = "0x1234bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb5678"
    assert lookalike(fake, real)
    assert not lookalike(real, real)
    assert not lookalike("0x9999bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb5678", real)


def info(
    i: int,
    src: str,
    dst: str,
    *,
    amount: int = 1,
    token_address: str = USDT,
    tx: str = "0x1",
    category: str = "erc20",
) -> TransferInfo:
    return TransferInfo(i, tx, category, src, dst, token_address, Decimal(amount))


def test_transfer_rules() -> None:
    wallet = addr(1)
    real = "0x1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa5678"
    fake = "0x1234bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb5678"
    airdrop_token = addr(0xD0)
    transfers = [
        info(1, wallet, real, amount=100),  # genuine payment
        info(2, wallet, addr(9), amount=0),  # wallet's own zero transfer: allowed
        info(3, addr(9), wallet, amount=0),  # poisoning transferFrom
        info(4, fake, wallet, amount=5, tx="0x2"),  # look-alike of a real counterparty
        info(5, addr(8), wallet, token_address=addr(0xBAD), tx="0x3"),  # spam token
        *[
            info(10 + i, addr(7), addr(100 + i), token_address=airdrop_token, tx="0x4")
            for i in range(3)
        ],
        info(20, addr(6), wallet, amount=0, category="erc721", token_address=addr(0xE0)),  # NFT
    ]
    reasons = transfer_spam_reasons(
        transfers,
        tracked={wallet},
        spam_tokens={addr(0xBAD)},
        verified_tokens={USDT},
        real_counterparties={wallet: {real}},
        config=CONFIG,
    )
    assert reasons == {
        3: "zero_value",
        4: "lookalike_address",
        5: "spam_token",
        10: "mass_airdrop",
        11: "mass_airdrop",
        12: "mass_airdrop",
    }
