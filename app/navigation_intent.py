"""Conservative text controls; ambiguous model actions must not end navigation."""
import re


THANKS_REPLY = "很开心能帮助您，还有其他需要导航的地方吗？"


def normalized(text: str) -> str:
    return re.sub(r"[\s，。！？!?、；;,.：:“”\"'（）()]+", "", text)


def is_acknowledgement(text: str) -> bool:
    return re.fullmatch(
        r"(?:好的|好|嗯|哦|明白了|知道了|了解了|收到|谢谢您|谢谢你|谢谢|多谢|感谢您|感谢你|感谢|太感谢了|辛苦了)+",
        normalized(text),
    ) is not None


def is_end_request(text: str) -> bool:
    return re.fullmatch(
        r"(?:(?:请|麻烦|帮我|我想|我要|现在|先|我|好的|好|嗯|谢谢您|谢谢你|谢谢))*"
        r"(?:(?:结束|取消|停止|退出|关闭)(?:当前|本次|这次|这个)?导航|"
        r"(?:不用|不需要|不想|无需)(?:再|继续)?导航(?:了)?|不导航了|结束|取消)"
        r"(?:(?:吧|了|一下|谢谢您|谢谢你|谢谢))*",
        normalized(text),
    ) is not None
