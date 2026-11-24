from sukpago.quality import (has_repetition, has_traditional_mongolian, is_cyrillic_mongolian,
                             peak_rss_mb)


def test_mongolian_script_detection():
    assert is_cyrillic_mongolian("Анхаарлаа төвлөрүүл.")
    assert not has_traditional_mongolian("Анхаарлаа төвлөрүүл.")
    trad = "ᠮᠣᠩᠭᠣᠯ ᠬᠡᠯᠡ"
    assert has_traditional_mongolian(trad)
    assert not is_cyrillic_mongolian(trad)
    assert not is_cyrillic_mongolian("Please focus.")


def test_russian_and_serbian_are_not_khalkha():
    assert not is_cyrillic_mongolian("Это проблема мира, которая встретила меня пять лет назад.")
    assert not is_cyrillic_mongolian("Свет костима ће продужати се до следећег дана.")
    assert not is_cyrillic_mongolian("Але, если се одно и удасться, це є проблем.")


def test_real_khalkha_passes_including_short_without_special_letters():
    assert is_cyrillic_mongolian("Ирэх долоо хоногийн мягмар гараг хүртэл гэрийн даалгавраа өгнө үү.")
    assert is_cyrillic_mongolian("Ойлгов уу?")


def test_repetition_words():
    loop = ("it's really easy to go to a website that explains virtue, and it's really easy to go "
            "to a website that explains virtue, and it's really easy to go to a website")
    assert has_repetition(loop)
    assert not has_repetition("Please submit your homework by next Tuesday.")


def test_repetition_chars_for_chinese():
    assert has_repetition("解释论文解释论文解释论文")
    assert not has_repetition("请在下周二之前提交作业。")


def test_peak_rss_is_plausible():
    assert 10 < peak_rss_mb() < 100_000
