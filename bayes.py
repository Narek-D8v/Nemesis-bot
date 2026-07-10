import math
import re
import aiosqlite

from typing import Tuple, Dict, List


class BayesClassifier:
    def __init__(self, db_path: str, model_name: str = 'default'):
        self.db_path = db_path
        self.model_name = model_name
        self.spam_total = 0
        self.ham_total = 0

    async def _load_counts(self):
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT spam_total, ham_total FROM bayes_counts WHERE model_name = ?",
                (self.model_name,)
            )
            row = await cursor.fetchone()
            if row:
                self.spam_total, self.ham_total = row
            else:
                self.spam_total = 0
                self.ham_total = 0

    async def _ensure_counts_row(self):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT INTO bayes_counts (model_name, spam_total, ham_total) VALUES (?, 0, 0) ON CONFLICT(model_name) DO NOTHING",
                (self.model_name,)
            )
            await conn.commit()

    async def _increment_count(self, field: str, amount: int = 1):
        async with aiosqlite.connect(self.db_path) as conn:
            if field == 'spam_total':
                await conn.execute(
                    "UPDATE bayes_counts SET spam_total = spam_total + ? WHERE model_name = ?",
                    (amount, self.model_name)
                )
                self.spam_total += amount
            else:
                await conn.execute(
                    "UPDATE bayes_counts SET ham_total = ham_total + ? WHERE model_name = ?",
                    (amount, self.model_name)
                )
                self.ham_total += amount
            await conn.commit()

    def _clean_word(self, word: str) -> str:
        return re.sub(r'[^a-zа-я0-9]', '', word.lower())

    def _tokenize(self, text: str) -> List[str]:
        text = re.sub(r'https?://\S+', '[URL]', text)
        text = re.sub(r'@\w+', '[MENTION]', text)
        text = re.sub(r't\.me/\S+', '[INVITE]', text)
        words = text.split()
        result = []
        for w in words:
            cleaned = self._clean_word(w)
            if cleaned:
                result.append(cleaned)
        return result

    async def train(self, text: str, is_spam: bool):
        tokens = self._tokenize(text)
        if not tokens:
            return

        await self._load_counts()
        await self._ensure_counts_row()
        await self._increment_count('spam_total' if is_spam else 'ham_total')

        async with aiosqlite.connect(self.db_path) as conn:
            for token in set(tokens):
                if not token:
                    continue
                spam_inc = 1 if is_spam else 0
                ham_inc = 0 if is_spam else 1
                await conn.execute(
                    """INSERT INTO bayes_stats (model_name, word, spam_count, ham_count) VALUES (?, ?, ?, ?)
                       ON CONFLICT(model_name, word) DO UPDATE SET
                         spam_count = spam_count + ?,
                         ham_count = ham_count + ?""",
                    (self.model_name, token, spam_inc, ham_inc, spam_inc, ham_inc)
                )
            await conn.commit()

    async def train_bulk(self, texts: List[str], is_spam: bool):
        for text in texts:
            await self.train(text, is_spam)

    async def get_word_probability(self, word: str) -> Tuple[float, float]:
        cleaned = self._clean_word(word)
        if not cleaned:
            return 0.5, 0.5
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT spam_count, ham_count FROM bayes_stats WHERE model_name = ? AND word = ?",
                (self.model_name, cleaned)
            )
            row = await cursor.fetchone()
        if row:
            spam_count, ham_count = row
        else:
            spam_count, ham_count = 0, 0

        alpha = 1
        spam_prob = (spam_count + alpha) / (self.spam_total + alpha * 2) if self.spam_total > 0 else 0.5
        ham_prob = (ham_count + alpha) / (self.ham_total + alpha * 2) if self.ham_total > 0 else 0.5
        return spam_prob, ham_prob

    async def classify(self, text: str) -> Tuple[bool, float]:
        await self._load_counts()
        tokens = self._tokenize(text)
        if not tokens:
            return False, 0.0

        total = self.spam_total + self.ham_total
        if total == 0:
            return False, 0.0

        total_spam = self.spam_total / total
        total_ham = self.ham_total / total

        unique_tokens = list(dict.fromkeys(tokens))

        async with aiosqlite.connect(self.db_path) as conn:
            placeholders = ",".join("?" for _ in unique_tokens)
            cursor = await conn.execute(
                f"SELECT word, spam_count, ham_count FROM bayes_stats WHERE model_name = ? AND word IN ({placeholders})",
                (self.model_name, *unique_tokens)
            )
            word_data = {row[0]: (row[1], row[2]) for row in await cursor.fetchall()}

        log_spam = math.log(total_spam)
        log_ham = math.log(total_ham)

        for token in unique_tokens:
            if token in word_data:
                w_spam, w_ham = word_data[token]
            else:
                w_spam = w_ham = 0
            spam_prob = max(0.01, min(0.99, (w_spam / total_spam) / ((w_spam / total_spam) + (w_ham / total_ham)))) if (w_spam + w_ham) > 0 else 0.4
            log_spam += math.log(max(spam_prob, 1e-10))
            log_ham += math.log(max(1 - spam_prob, 1e-10))

        try:
            spam_prob_val = math.exp(log_spam)
            ham_prob_val = math.exp(log_ham)
            total_prob = spam_prob_val + ham_prob_val
            if total_prob == 0:
                return False, 0.0
            confidence = spam_prob_val / total_prob
            return confidence > 0.5, confidence
        except OverflowError:
            return True, 1.0

    async def get_stats(self) -> Dict:
        await self._load_counts()
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM bayes_stats WHERE model_name = ?",
                (self.model_name,)
            )
            vocab_size = (await cursor.fetchone())[0]
        return {
            'spam_total': self.spam_total,
            'ham_total': self.ham_total,
            'vocab_size': vocab_size,
            'total': self.spam_total + self.ham_total,
            'model_name': self.model_name,
        }
