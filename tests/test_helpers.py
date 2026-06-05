from app.utils.helpers import format_toman, generate_referral_code, paginate_meta


def test_generate_referral_code_unique_length():
    codes = {generate_referral_code() for _ in range(100)}
    assert all(len(c) == 8 for c in codes)
    assert len(codes) > 90  # overwhelmingly unique


def test_format_toman():
    assert format_toman(1000000) == "1,000,000 تومان"


def test_paginate_meta():
    offset, pages = paginate_meta(total=12, page=2, page_size=5)
    assert offset == 5
    assert pages == 3
    # clamps overflow page
    offset, pages = paginate_meta(total=12, page=99, page_size=5)
    assert offset == 10
