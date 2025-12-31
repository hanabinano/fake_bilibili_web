from collections import deque, defaultdict
import time


# --- 1. AC 自动机（敏感词过滤） ---
class ACNode:
    def __init__(self):
        self.children = {}
        self.fail = None
        self.is_end = False
        self.length = 0


class ACAutomaton:
    def __init__(self, keywords):
        self.root = ACNode()
        for word in keywords:
            self.insert(word)
        self.build_fail()

    def insert(self, word):
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = ACNode()
            node = node.children[char]
        node.is_end = True
        node.length = len(word)

    def build_fail(self):
        queue = deque()
        for _, child in self.root.children.items():
            child.fail = self.root
            queue.append(child)

        while queue:
            current = queue.popleft()
            for key, child in current.children.items():
                fail_node = current.fail
                while fail_node and key not in fail_node.children:
                    fail_node = fail_node.fail
                child.fail = fail_node.children[key] if fail_node and key in fail_node.children else self.root
                queue.append(child)

    def filter(self, text):
        if not text:
            return ""
        node = self.root
        result = list(text)
        for i, char in enumerate(text):
            while node and char not in node.children:
                node = node.fail
            if not node:
                node = self.root
                continue
            node = node.children[char]
            temp = node
            while temp != self.root:
                if temp.is_end:
                    for j in range(i - temp.length + 1, i + 1):
                        result[j] = "*"
                temp = temp.fail
        return "".join(result)


# --- 2. 弹幕管理器 ---
class DanmakuManager:
    def __init__(self):
        self.time_queue = []
        self.user_history = defaultdict(list)
        self.ac_filter = ACAutomaton(["404"])

    def add_danmaku(self, user_id, content, video_time, color):
        clean_content = self.ac_filter.filter(content)
        dm_obj = {
            "time": float(video_time),
            "content": clean_content,
            "color": color,
            "user_id": user_id,
            "timestamp": time.time(),
        }
        inserted = False
        for i, dm in enumerate(self.time_queue):
            if dm["time"] > video_time:
                self.time_queue.insert(i, dm_obj)
                inserted = True
                break
        if not inserted:
            self.time_queue.append(dm_obj)
        self.user_history[user_id].append(dm_obj)
        return dm_obj

    def get_danmaku(self):
        return self.time_queue

    def search_by_user(self, user_id):
        return self.user_history.get(user_id, [])

    def search_by_keyword(self, keyword):
        return [dm for dm in self.time_queue if keyword in dm["content"]]

    def get_peak_stats(self):
        if not self.time_queue:
            return {"peak_second": 0, "count": 0}
        try:
            buckets = defaultdict(int)
            for dm in self.time_queue:
                bucket_key = int(dm["time"])
                buckets[bucket_key] += 1
            if not buckets:
                return {"peak_second": 0, "count": 0}
            peak_sec = max(buckets, key=buckets.get)
            return {"peak_second": peak_sec, "count": buckets[peak_sec]}
        except Exception as e:
            print(f"Error in stats: {e}")
            return {"peak_second": 0, "count": 0}

    def set_filter_words(self, words):
        if not words:
            words = ["404"]
        self.ac_filter = ACAutomaton(words)


manager = DanmakuManager()
