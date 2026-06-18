---
contest_id: 1
problem_index: A
algorithm: math
difficulty: easy
rating: 1000
url: https://codeforces.com/contest/1/problem/A
status: AC         # pending | WA | AC | abandoned
attempts: 2
last_verdict: AC
last_submit: 2025-01-15
---

## 题目

给定 n×m 的广场，用 a×a 的石板铺满，求最少石板数。

## 我的解题思路

用向上取整：⌈n/a⌉ × ⌈m/a⌉

## 错误历史

### 第1次：WA（第2个测试点）
- 错误类型：整除截断
- Agent 提示：检查整数除法是否会漏掉余数

### 第2次：AC ✅