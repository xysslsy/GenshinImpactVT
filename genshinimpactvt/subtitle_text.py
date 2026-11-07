"""Small, deterministic rules shared by all subtitle sources."""
import re
import time

DEFAULT_REGION = (0.06, 0.68, 0.88, 0.29)


def normalize_text(text):
    return re.sub(r'\s+', '', str(text or ''))[:500]


def valid_region(value):
    try:
        x, y, w, h = map(float, value)
        if 0 <= x < 1 and 0 <= y < 1 and .02 <= w <= 1 and .02 <= h <= 1 and x+w <= 1.001 and y+h <= 1.001:
            return x, y, w, h
    except (TypeError, ValueError):
        pass
    return DEFAULT_REGION


def directions(text):
    text = normalize_text(text)
    # A sequence of instructions must not look like a diagonal direction.
    text = re.split(r'然后|接着|随后|再(?:往|向|朝|走|去)', text)[0]
    text = re.sub(r'东西南北|东西(?:方)?|北京|南京|东京|西瓜|东北虎|东风|南瓜', '', text)
    # Spoken route language: 正北、北偏东、东北角、朝着西边、东面那个方向。
    text = re.sub(r'北偏东|东偏北','东北',text)
    text = re.sub(r'南偏东|东偏南','东南',text)
    text = re.sub(r'北偏西|西偏北','西北',text)
    text = re.sub(r'南偏西|西偏南','西南',text)
    text = re.sub(r'(?:不要|别|不能|不是|不往|不向|不朝)[^，。；！？,;!?]{0,6}?[东西南北](?:[东西南北])?(?:方向|边|方)?', '', text)
    found = set()
    for match in re.finditer(r'[东西南北]{1,2}', text):
        word = match.group()
        before, after = text[max(0, match.start()-4):match.start()], text[match.end():match.end()+4]
        if text == word or text == '正'+word or re.search(r'往|向|朝|面|转|偏', before) or re.match(r'方向|边|方|侧|面|角|走|前进|这边', after):
            found.update(word)
    return found


def direction_steps(text):
    """Sequential phrases with proportional offsets inside a timed subtitle cue."""
    text=normalize_text(text)
    start=0;steps=[]
    for match in re.finditer(r'然后|接着|随后|再(?=往|向|朝|走|去)',text):
        phrase=text[start:match.start()]
        if directions(phrase):steps.append((start/max(1,len(text)),phrase))
        start=match.end()
    phrase=text[start:]
    if directions(phrase):steps.append((start/max(1,len(text)),phrase))
    return steps


class StableText:
    """Two matching OCR observations; DOM cues are already timed text."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.pending = ''; self.count = 0; self.when = 0.; self.last = ''

    def observe(self, text, source, now=None):
        now = time.monotonic() if now is None else now
        text = normalize_text(text)
        if not text:
            self.pending = ''; self.count = 0
            # Allow the same instruction to recur after an empty subtitle.
            self.last = ''
            return None
        if source == 'ocr':
            self.count = self.count + 1 if text == self.pending and now-self.when < 2 else 1
            self.pending = text; self.when = now
            if self.count < 2:
                return None
        if text == self.last:
            return None
        self.last = text
        return text
