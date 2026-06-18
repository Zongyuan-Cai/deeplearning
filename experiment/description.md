1. 项目背景

当前自动搜索/auto research 系统大多采用：

随机搜索（random search）
贪心搜索（greedy search）
或简单基于历史的尝试

这些方法的核心问题是：

❗ 缺乏“方向控制”，搜索效率低、容易陷入局部最优。

本项目引入一个新机制：

Bias（动态方向偏置）

目标是让系统从：

无方向搜索 → 有方向控制的搜索
2. 项目目标

实现一个实验系统，用于验证：

G1：有效性

Dynamic Bias Search 是否优于：

Random Search
Greedy Search
Reflection-only Search
G2：机制验证

证明 bias：

改变了搜索轨迹
提高了搜索效率
不是简单的文本总结
G3：可解释性

系统能够输出：

搜索轨迹
bias 演化过程
参数变化趋势
3. 核心功能

系统必须支持以下能力：

F1：统一实验框架

支持统一 loop：

候选生成 → 执行 → 评估 → reflection → bias更新 → 下一轮
F2：多搜索方法对比

必须实现 4 种方法：

方法	描述
Random	完全随机
Greedy	围绕 best 搜索
Reflection-only	有反思，无 bias
Dynamic Bias	有反思 + bias
F3：任务执行系统

支持：

超参数搜索任务
自动运行训练
返回 score
F4：Bias 系统

支持：

bias 状态维护
bias 动态更新
bias 影响候选生成
F5：Reflection 系统

支持：

分析历史结果
输出结构化总结
F6：日志与轨迹记录

每轮完整记录：

候选
score
reflection
bias
best-so-far
F7：结果分析

输出：

曲线图
指标统计
bias 演化分析
4. 非功能要求
N1：可复现
支持 random seed
所有实验可重复
N2：可扩展

后续可扩展到：

多任务
LLM任务
auto research
N3：低耦合

模块独立：

task
method
bias
logging
5. 系统架构
                ┌──────────────┐
                │ Experiment   │
                │   Runner     │
                └──────┬───────┘
                       │
        ┌──────────────▼──────────────┐
        │        Method Layer          │
        │ random / greedy / bias       │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │     Candidate Generator      │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │        Task Executor         │
        │     (train + evaluate)       │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   Reflection & Bias Engine   │
        └──────────────┬──────────────┘
                       │
                ┌──────▼──────┐
                │   Logger     │
                └─────────────┘
6. 模块设计
6.1 Experiment Runner
功能
控制实验流程
调度各模块
输入
{
  "task": "small_hpo",
  "method": "dynamic_bias",
  "rounds": 30,
  "seeds": 5
}
输出
实验结果文件
曲线图
6.2 Task Module
功能
执行训练
返回 score
输入
{
  "learning_rate": 0.001,
  "weight_decay": 0.01,
  "dropout": 0.2
}
输出
{
  "score": 0.82
}
6.3 Candidate Generator
功能

生成下一轮候选。

支持模式
无 bias
有 bias
6.4 Reflection Engine
输入
历史候选
历史 score
输出
{
  "summary": "...",
  "successful_patterns": [...],
  "failed_patterns": [...],
  "search_state": "local_refinement"
}
6.5 Bias Engine
输入
reflection
历史记录
输出
{
  "preferred_changes": {
    "learning_rate": "decrease",
    "dropout": "keep"
  },
  "exploration_level": 0.3
}
要求
每轮更新
影响候选生成
6.6 Logger
每轮记录字段
{
  "round": 1,
  "method": "dynamic_bias",
  "candidate": {...},
  "score": 0.82,
  "best_score": 0.82,
  "reflection": {...},
  "bias_before": {...},
  "bias_after": {...}
}
7. 实验设计
7.1 主实验

方法：

Random
Greedy
Reflection-only
Dynamic Bias
7.2 消融实验

必须实现：

无 reflection
静态 bias
打乱 bias
8. 指标定义
8.1 结果指标
final_best_score
avg_best_score
8.2 效率指标
rounds_to_threshold
best_score_under_budget
8.3 轨迹指标
score 曲线
参数变化趋势
bias 变化趋势
9. 输出结果
必须生成：
图 1

best-so-far 曲线

图 2

score 曲线

图 3

参数轨迹

图 4

bias 演化

10. CLI接口

必须支持：

python run_experiment.py \
  --task small_hpo \
  --method dynamic_bias \
  --rounds 30 \
  --seeds 5
11. 目录结构（强制）
experiment/
├── core/
├── methods/
├── task/
├── bias/
├── reflection/
├── logging/
├── analysis/
├── run_experiment.py
12. 优先级
P0（必须完成）
Random / Greedy / Dynamic Bias
单任务可跑
日志记录
曲线输出
P1
Reflection-only
基础消融实验
P2
完整消融
bias 可视化
13. 验收标准

满足以下条件视为完成：

四种方法可运行
实验结果可复现
能输出曲线图
Dynamic Bias 明显优于 Random
打乱 bias 后性能下降