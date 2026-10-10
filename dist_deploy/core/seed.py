"""初始演示数据：账号、知识点、题库、新闻、课程、直播、帖子、文件、优惠券。

真实部署时把本模块的 seed_all() 换成正式导入即可；结构不变。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import auth, backup, commerce, courses, db, files, forum, knowledge, live, news, notify, quiz, users


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def is_seeded() -> bool:
    return int(db.scalar("SELECT COUNT(*) FROM users", (), 0)) > 0


# ============================ 账号 ============================
def seed_users() -> dict:
    ids: dict[str, int] = {}
    # 管理员
    if not auth.get_user_by_name("admin"):
        uid = auth.register("admin", "123456", email="admin@bgl.ai")
        db.execute("UPDATE users SET role='admin', nickname='平台管理员', avatar='🛡️', "
                   "bio='BGL 学习平台运营', realname_status='approved', phone='13800000000', "
                   "phone_verified=1, email_verified=1, points=9999, level=10 WHERE id=?", (uid,))
        ids["admin"] = uid
    else:
        ids["admin"] = auth.get_user_by_name("admin")["id"]

    demo = [
        ("fangyuan", "方圆", "🧑‍💻", "用 AI 做点有用的东西", 860),
        ("liyuan", "李明远", "👨‍🏫", "大模型方向讲师，前一线大厂算法工程师", 1580),
        ("wangxue", "王雪", "👩‍🏫", "提示词工程与 AI 产品设计", 1240),
        ("xiaoai", "小艾", "🐣", "AI 学习第 30 天，每天进步一点点", 320),
        ("azhe", "阿哲", "🦉", "正在从后端转向 AI 应用开发", 610),
        ("chenmo", "陈默", "🐼", "数据科学在读，关注微调与评估", 450),
    ]
    for uname, nick, av, bio, pts in demo:
        u = auth.get_user_by_name(uname)
        if u:
            ids[uname] = u["id"]
            continue
        uid = auth.register(uname, "123456")
        db.execute("UPDATE users SET nickname=?, avatar=?, bio=?, points=?, level=? WHERE id=?",
                   (nick, av, bio, pts, auth.level_of(pts), uid))
        ids[uname] = uid

    # 讲师认证
    for uname, intro, field, level in [
        ("liyuan", "十年一线算法经验，主讲大模型原理与微调实战，累计学员 5000+。", "大模型基础 / 微调实战", 4),
        ("wangxue", "AI 产品与提示词工程专家，服务过多家企业的 AI 落地项目。", "提示词工程 / AI 应用开发", 3),
    ]:
        db.execute("UPDATE users SET instructor_status='approved', role='instructor', "
                   "instructor_intro=?, instructor_field=?, instructor_level=?, "
                   "realname_status='approved' WHERE id=?", (intro, field, level, ids[uname]))

    # 关注关系
    pairs = [("fangyuan", "liyuan"), ("fangyuan", "wangxue"), ("xiaoai", "liyuan"),
             ("azhe", "liyuan"), ("chenmo", "wangxue"), ("liyuan", "fangyuan"),
             ("wangxue", "fangyuan"), ("xiaoai", "fangyuan")]
    for a, b in pairs:
        db.execute("INSERT OR IGNORE INTO follows(follower_id,followee_id,created_at) VALUES(?,?,?)",
                   (ids[a], ids[b], db.now_str()))
    return ids


# ============================ 知识点 ============================
KNOWLEDGE = [
    ("大模型基础", "Transformer 架构全景", "理解 Encoder/Decoder 堆叠、残差与 LayerNorm 的作用，是读懂一切大模型论文的起点。",
     "Transformer 把「序列建模」拆成两个可并行的子层：多头自注意力负责在任意两个位置之间建立联系，前馈网络负责对每个位置做非线性变换。"
     "每个子层外面都套了一层残差连接（Residual）和层归一化（LayerNorm），残差保证梯度能跨层直通，LayerNorm 稳定每一层的数值分布。"
     "训练时靠位置编码注入顺序信息——因为注意力本身对位置是「无序」的。",
     "Attention(Q,K,V) = softmax(QKᵀ/√d_k)·V", "", "入门"),
    ("大模型基础", "注意力机制：为什么它能替代 RNN", "QKV 三元组、缩放点积、多头并行的直觉解释。",
     "注意力的本质是「加权求和」：用 Query 和每个 Key 做点积得到相关性分数，softmax 归一化成权重，再对 Value 加权求和。"
     "相比 RNN 的逐步递推，注意力的路径长度是 O(1)——任意两个位置一步可达，所以长距离依赖不会衰减；代价是 O(n²) 的计算量。"
     "缩放因子 √d_k 的作用是把点积的方差拉回 1 附近，避免 softmax 进入饱和区导致梯度消失。",
     "MultiHead = Concat(head₁,…,head_h)·W^O", "", "入门"),
    ("大模型基础", "Token、上下文窗口与位置编码", "为什么「字数」不等于 token 数，上下文窗口如何决定成本与能力边界。",
     "模型看到的不是字符而是 token。中文常见 1 个字 ≈ 1–1.5 个 token，英文约 1 个词 ≈ 1.3 个 token。"
     "上下文窗口（Context Window）是单次推理能容纳的最大 token 数，它同时决定三件事：能塞进多少资料、显存占用、以及单位请求的成本。"
     "长上下文并不等于「记得住」——中间位置的信息容易被忽略（Lost in the Middle 现象），关键内容建议放在开头或结尾。",
     "", "", "入门"),
    ("大模型基础", "预训练、SFT 与涌现能力", "三个阶段的目标差异，以及「规模带来能力突现」的经验规律。",
     "预训练（Pre-training）用海量无标注语料做下一 token 预测，得到的是「语言的统计规律」；"
     "监督微调（SFT）用指令-回答对把模型对齐到「听指令」的形态；强化学习（RLHF/DPO）再对齐到人类偏好。"
     "涌现（Emergence）指某些能力在小模型上几乎为零、跨过某个规模阈值后突然出现——它在工程上的启示是："
     "能力不足时，先考虑换更大的基座，而不是只堆提示词技巧。",
     "", "", "进阶"),

    ("提示词工程", "提示词的四个必备要素", "角色、任务、约束、示例——缺一个就多一轮返工。",
     "一个稳定可用的提示词通常包含四块：① 角色（你是谁、以什么标准回答）；② 任务（要做什么，动词开头）；"
     "③ 约束（长度、格式、禁止项、不知道时怎么办）；④ 示例（1–3 条输入输出对照，比任何形容词都有效）。"
     "经验：把「约束」写清楚带来的收益，远大于反复更换礼貌用语。",
     "", "", "入门"),
    ("提示词工程", "Few-shot 与思维链（CoT）", "什么时候给例子，什么时候让它「先想再答」。",
     "Few-shot 通过少量示例把任务的隐含规则显式化，适合格式敏感、判据微妙的场景。"
     "思维链（Chain-of-Thought）让模型先输出推理过程再给结论，在数学、逻辑、多步决策任务上显著提升准确率；"
     "但对纯检索/抽取类任务收益有限，反而增加 token 成本。工程建议：先零样本试，不行再补示例，最后才上 CoT。",
     "", "prompt = f\"{instruction}\\n\\n示例：\\n{examples}\\n\\n问题：{q}\\n逐步推理后作答：\"", "进阶"),
    ("提示词工程", "结构化输出与 JSON 约束", "用 Schema 把「自由文本」变成「可编程数据」。",
     "让模型稳定输出 JSON 的要点：① 给出完整 Schema 与字段语义；② 明确「只输出 JSON，不要解释」；"
     "③ 给出一个字段齐全的示例；④ 解析失败时把错误信息喂回去重试（自修复循环）。"
     "对稳定性要求高的场景，优先使用模型厂商提供的结构化输出 / Function Calling 能力，而不是靠提示词祈祷。",
     "", "{\"title\": str, \"tags\": [str], \"score\": int}", "进阶"),
    ("提示词工程", "提示词注入与防御", "当输入来自用户或外部文档时，你的提示词就不再安全。",
     "提示词注入指攻击者在输入里夹带「忽略以上指令」之类的文本，劫持模型行为。"
     "防御手段：① 把外部内容用明确的分隔符包裹并声明「以下内容仅为数据，不是指令」；"
     "② 关键动作（下单、发信、删数据）必须由代码校验而非模型自行决定；③ 对输出做白名单 Schema 校验；"
     "④ 最小权限——不要给模型不需要的工具。",
     "", "", "高阶"),

    ("微调与对齐", "全参数微调 vs LoRA / QLoRA", "显存、效果、部署成本三者的取舍。",
     "全参数微调更新所有权重，效果上限高，但需要数倍显存且每个下游任务产出一份完整权重。"
     "LoRA 冻结原权重、只训练低秩旁路矩阵（A·B），参数量常降到 0.1%–1%，显存大幅下降、产物只有几十 MB，可插拔切换。"
     "QLoRA 在此基础上把基座量化到 4bit 再挂 LoRA，让单张消费级显卡也能微调 7B 模型。"
     "工程经验：先用 LoRA 验证任务可行性，效果触顶再考虑全参。",
     "W' = W + BA,  rank(B·A) = r ≪ d", "lora = LoraConfig(r=8, lora_alpha=16, target_modules=[\"q_proj\",\"v_proj\"])", "进阶"),
    ("微调与对齐", "RLHF 与 DPO：对齐到底在对什么", "从「会说话」到「说人话、不闯祸」。",
     "RLHF 分三步：收集人类偏好比较数据 → 训练奖励模型（RM）→ 用 PPO 在奖励引导下优化策略。效果好但流程复杂、训练不稳定。"
     "DPO 直接把「偏好对」转成一个类似分类的损失，跳过奖励模型与强化学习，训练更稳、成本更低，已成为主流替代方案。"
     "对齐的代价：过度对齐会导致「安全但无用」，需要用偏好数据的多样性来平衡。",
     "L_DPO = -log σ(β·[log π(y_w)/π_ref(y_w) − log π(y_l)/π_ref(y_l)])", "", "高阶"),
    ("微调与对齐", "指令数据质量与配比", "数据决定上限：1000 条干净数据 > 10 万条噪声。",
     "微调数据的三个关键：① 覆盖度——任务类型、长度分布、指令风格要与你真实的调用分布一致；"
     "② 质量——错答、答非所问、格式不一致的样本会直接被模型学走；③ 配比——通用能力数据与领域数据混编，防止「学新忘旧」。"
     "实用做法：先人工精修 500 条种子数据跑通流程，再用强模型批量扩增 + 人工抽检。",
     "", "", "进阶"),
    ("微调与对齐", "灾难性遗忘与缓解", "微调后模型「变笨了」怎么办。",
     "灾难性遗忘指微调把通用能力覆盖掉，表现为除了新任务之外什么都答不好。"
     "缓解手段：① 降低学习率、缩短训练轮数（1–3 epoch 通常足够）；② 混入 5%–20% 通用指令数据；"
     "③ 用 LoRA 而非全参更新；④ 训练后做「能力回归测试」，把通用题集当成回归用例常态化跑。",
     "", "", "高阶"),

    ("RAG 与向量检索", "向量嵌入与相似度度量", "把语义变成可计算的向量距离。",
     "嵌入模型把文本映射为稠密向量，语义相近的文本在向量空间中距离更近。"
     "常用度量：余弦相似度（关注方向，最常用）、点积（对模长敏感，适合归一化后的向量）、欧氏距离。"
     "选择嵌入模型要看三件事：中文效果、支持的输入长度、以及向量维度带来的存储成本。",
     "cos(a,b) = (a·b) / (‖a‖‖b‖)", "", "入门"),
    ("RAG 与向量检索", "切分策略与 MMR 去冗", "切得太碎丢上下文，切得太大稀释相关性。",
     "文档切分要在「语义完整」与「检索精度」之间平衡：常见做法是按标题层级切，再对超长块做滑动窗口重叠（overlap 10%–20%）。"
     "检索出 Top-K 后往往高度冗余，用 MMR（最大边际相关性）在「相关性」和「多样性」之间取折中，"
     "公式上通过 λ 调节：λ=1 只看相关，λ=0 只看多样。",
     "MMR = argmax[λ·sim(d,q) − (1−λ)·max sim(d,d_j)]", "", "进阶"),
    ("RAG 与向量检索", "重排序（Rerank）与检索质量", "召回靠向量，精度靠重排。",
     "两阶段检索：先用向量做粗召回（快、便宜、召回率高），再用交叉编码器（Cross-Encoder）对候选逐条精排（慢、准）。"
     "重排序能显著提升 Top-3 命中率，是 RAG 系统性价比最高的优化点之一。"
     "评估要用「检索指标」（Recall@K、MRR）而不是只看最终回答，否则无法定位问题出在检索还是生成。",
     "", "", "进阶"),
    ("RAG 与向量检索", "RAG 的失败模式清单", "检索错、上下文挤、答案编——三种典型故障与对策。",
     "① 检索不到：检查切分粒度、嵌入模型是否匹配语言、Top-K 是否过小；"
     "② 检索到了但没用上：上下文过长导致「中间遗忘」，或提示词没要求「必须基于给定资料回答」；"
     "③ 检索到错的还照答：加入引用约束（回答必须标出来源段落），并在提示词里允许「资料不足时明确说不知道」。",
     "", "", "高阶"),

    ("AI 应用开发", "Function Calling 与工具调用", "让模型从「会说」变成「会做」。",
     "Function Calling 让模型输出结构化的调用意图（函数名 + 参数），由你的代码真正执行。"
     "关键设计：① 工具描述要写清「什么时候用」而不只是「是什么」；② 参数用 JSON Schema 严格约束；"
     "③ 执行结果要回填给模型并允许它继续多轮决策；④ 危险操作必须由代码二次确认。",
     "", "tools=[{\"name\":\"search\",\"parameters\":{\"type\":\"object\",\"properties\":{\"q\":{\"type\":\"string\"}}}}]", "进阶"),
    ("AI 应用开发", "Agent 循环与终止条件", "ReAct、最大步数、以及「怎么知道它做完了」。",
     "Agent = 模型 + 工具 + 循环。每一轮：观察 → 思考 → 选择动作 → 执行 → 把结果作为新观察。"
     "工程上必须设三个保险：最大步数上限、单步超时、以及「无进展检测」（连续两轮动作相同则强制终止）。"
     "没有终止条件的 Agent 是生产事故的常见来源。",
     "", "for step in range(MAX_STEPS):\\n    act = llm.decide(state)\\n    if act.done: break", "进阶"),
    ("AI 应用开发", "流式输出、并发与成本控制", "体验、吞吐、账单三件事一起优化。",
     "流式输出（SSE/WebSocket）把首 token 延迟作为体验指标而非总耗时；"
     "并发方面用异步请求池批量调用，注意供应商的 QPS 与 TPM 限制；"
     "成本控制三板斧：缓存（相同请求直接命中）、模型分级路由（简单任务用小模型）、提示词瘦身（去掉无效的冗长指令）。",
     "", "", "进阶"),
    ("AI 应用开发", "微调 / RAG / 提示词：怎么选", "一张决策树替代无休止的争论。",
     "决策顺序建议：① 先写提示词，零样本不行就 Few-shot ——成本最低、迭代最快；"
     "② 需要私有知识且知识会变 → RAG（知识更新无需重训）；"
     "③ 需要固定风格 / 特定格式 / 领域术语稳定输出 → 微调；"
     "④ 需要「做动作」 → Function Calling / Agent。"
     "三者可叠加：RAG 提供事实，微调提供风格，提示词负责调度。",
     "", "", "入门"),

    ("评估与安全", "如何评估一个大模型应用", "没有评估集，就没有优化方向。",
     "最小可行评估：准备 50–200 条覆盖真实分布的问题 + 期望答案，定义可自动打分的指标"
     "（分类用准确率/F1，生成用「关键点命中率」或 LLM-as-Judge 打分）。"
     "每次改动后跑全量评估集，记录指标变化——这是把「感觉变好了」变成「确实变好了」的唯一办法。",
     "命中率 = 命中的关键点数 / 期望关键点总数", "", "进阶"),
    ("评估与安全", "幻觉的成因与抑制", "模型不是「不知道」，而是「必须说点什么」。",
     "幻觉来自三处：训练数据本身有误、模型被激励成「总是给出答案」、以及检索/上下文没提供依据。"
     "抑制手段：允许并鼓励模型回答「资料中没有」；强制引用来源；对数值/事实类问题做规则校验；"
     "把最终输出交给确定性代码做兜底校验，而不是完全信任生成结果。",
     "", "", "进阶"),
    ("评估与安全", "红队测试与提示词越狱", "在上线前，先自己攻击自己。",
     "红队测试清单：越权指令绕过、角色扮演诱导、多轮对话渗透、编码混淆（Base64/拼音）绕过关键词、"
     "以及数据外泄（诱导模型吐出系统提示词）。每次上线新功能前至少跑一遍标准攻击集，把通过的用例沉淀为回归测试。",
     "", "", "高阶"),
    ("评估与安全", "数据合规与内容边界", "能做什么，比能做成什么更重要。",
     "上线生成式功能需明确四件事：① 训练/调用数据的来源与授权；② 用户输入是否会回流用于训练（要给出开关与说明）；"
     "③ 生成内容的标识与追溯；④ 高风险领域（医疗、法律、金融）必须加入免责声明与人工复核入口。"
     "把这些写进隐私政策与用户协议，并在界面显著位置提示。",
     "", "", "高阶"),
]

QUESTIONS = [
    ("大模型基础", "single", "Transformer 中残差连接的主要作用是？",
     ["提升显存利用率", "让梯度可以跨层直通，缓解深层网络退化", "减少注意力计算量", "替代位置编码"],
     "B", "残差连接使梯度有一条恒等映射的直通路径，是深层网络可训练的关键。", "入门"),
    ("大模型基础", "single", "自注意力计算中对 QKᵀ 除以 √d_k 的目的是？",
     ["减少参数量", "防止点积过大导致 softmax 饱和、梯度消失", "加速矩阵乘法", "增强位置信息"],
     "B", "缩放使点积方差归一到 1 附近，避免 softmax 输出接近 one-hot。", "入门"),
    ("大模型基础", "judge", "上下文窗口越大，模型对中间位置信息的利用就越充分。",
     ["正确", "错误"], "B", "存在 Lost in the Middle 现象，中间位置的信息容易被忽略。", "进阶"),
    ("大模型基础", "single", "以下哪个阶段的目标是让模型「听懂指令」？",
     ["预训练", "监督微调 SFT", "分词器训练", "量化压缩"],
     "B", "SFT 用指令-回答对把模型对齐到听指令的形态。", "入门"),
    ("大模型基础", "multi", "关于 Token 的说法，正确的有？",
     ["中文 1 个字通常约 1–1.5 个 token", "Token 数直接决定显存与成本", "英文 1 个词约等于 1 个 token",
      "Token 与字符一一对应"],
     "A,B", "Token 与字符不是一一对应；英文 1 词约 1.3 token。", "进阶"),

    ("提示词工程", "single", "以下哪项不属于提示词四要素？",
     ["角色设定", "任务描述", "约束条件", "模型的学习率"],
     "D", "学习率是训练超参数，不属于提示词要素。", "入门"),
    ("提示词工程", "judge", "思维链（CoT）在所有任务上都能提升效果。",
     ["正确", "错误"], "B", "对纯检索/抽取类任务收益有限，反而增加 token 成本。", "进阶"),
    ("提示词工程", "single", "提高结构化输出稳定性的最可靠做法是？",
     ["在提示词里反复强调", "把 temperature 调到 2", "使用厂商提供的结构化输出 / Function Calling",
      "增加输出长度"],
     "C", "由运行时强约束 Schema 比靠提示词祈祷可靠得多。", "进阶"),
    ("提示词工程", "multi", "防御提示词注入的合理手段包括？",
     ["用分隔符包裹外部内容并声明其为数据", "关键动作由代码校验而非模型决定",
      "对输出做 Schema 白名单校验", "把系统提示词完整告诉用户"],
     "A,B,C", "泄露系统提示词会显著增加被绕过风险。", "高阶"),
    ("提示词工程", "single", "Few-shot 最主要的价值是？",
     ["降低 token 消耗", "把任务中隐含的判据与格式显式化", "提升模型参数量", "加快推理速度"],
     "B", "示例比任何形容词描述都更能传达隐性规则。", "入门"),

    ("微调与对齐", "single", "LoRA 相比全参数微调的核心优势是？",
     ["效果一定更好", "只训练低秩旁路，显存与产物体积大幅下降且可插拔",
      "不需要训练数据", "可以不用 GPU"],
     "B", "LoRA 参数量常降到 0.1%–1%，产物只有几十 MB。", "入门"),
    ("微调与对齐", "single", "DPO 相比 RLHF 的主要改进是？",
     ["完全不需要偏好数据", "跳过奖励模型与强化学习，训练更稳定",
      "只能用在小模型上", "不再需要 SFT"],
     "B", "DPO 直接把偏好对转成损失，流程大幅简化。", "高阶"),
    ("微调与对齐", "judge", "微调的 epoch 数越多，效果一定越好。",
     ["正确", "错误"], "B", "通常 1–3 epoch 足够，过多会导致过拟合与灾难性遗忘。", "进阶"),
    ("微调与对齐", "multi", "缓解灾难性遗忘的手段有？",
     ["降低学习率、减少训练轮数", "混入通用指令数据", "使用 LoRA 而非全参更新", "把数据集缩减到 10 条"],
     "A,B,C", "数据量太小只会让模型学不到东西，不能缓解遗忘。", "高阶"),
    ("微调与对齐", "single", "指令数据质量的第一要素是？",
     ["数量足够多", "与真实调用分布一致且答案正确", "全部来自网络抓取", "长度统一"],
     "B", "覆盖度与质量决定上限，1000 条干净数据胜过 10 万条噪声。", "进阶"),

    ("RAG 与向量检索", "single", "RAG 中重排序（Rerank）的主要作用是？",
     ["加快向量检索速度", "用交叉编码器对候选做精排，提升 Top-K 精度",
      "压缩向量维度", "替代嵌入模型"],
     "B", "两阶段检索：向量粗召回 + 交叉编码器精排。", "进阶"),
    ("RAG 与向量检索", "single", "MMR 算法调节的是什么？",
     ["相似度度量方式", "相关性与多样性之间的平衡", "切分块大小", "向量维度"],
     "B", "λ 越大越偏向相关性，越小越偏向多样性。", "进阶"),
    ("RAG 与向量检索", "judge", "文档切分得越碎，检索效果一定越好。",
     ["正确", "错误"], "B", "太碎会丢失上下文，需要与语义完整性平衡并设置重叠。", "进阶"),
    ("RAG 与向量检索", "multi", "RAG 检索不到内容时，可能的原因包括？",
     ["切分粒度过大导致语义被稀释", "嵌入模型与语种不匹配", "Top-K 设置过小", "用户没有登录"],
     "A,B,C", "是否登录与检索质量无关。", "高阶"),
    ("RAG 与向量检索", "single", "评估检索质量应优先看哪个指标？",
     ["最终回答的流畅度", "Recall@K 或 MRR", "生成 token 数", "响应时间"],
     "B", "只看最终回答无法区分问题出在检索还是生成。", "进阶"),

    ("AI 应用开发", "single", "Function Calling 中真正执行函数的是？",
     ["大模型自身", "你的应用程序代码", "向量数据库", "分词器"],
     "B", "模型只输出调用意图，执行必须由代码完成并做权限校验。", "入门"),
    ("AI 应用开发", "multi", "Agent 循环必须设置的安全阀包括？",
     ["最大步数上限", "单步超时", "无进展检测", "无限循环以追求最优解"],
     "A,B,C", "没有终止条件的 Agent 是生产事故常见来源。", "进阶"),
    ("AI 应用开发", "single", "以下哪种需求最适合用 RAG 而非微调？",
     ["固定输出风格的品牌文案", "私有知识且知识频繁更新", "教会模型一种新语言", "减少模型参数量"],
     "B", "知识会变时 RAG 无需重训，更新成本最低。", "入门"),
    ("AI 应用开发", "single", "控制 API 成本最直接的三招不包括？",
     ["结果缓存", "模型分级路由", "提示词瘦身", "把 temperature 设为 0.9"],
     "D", "temperature 主要影响随机性，不直接决定成本。", "进阶"),
    ("AI 应用开发", "judge", "流式输出主要优化的是首 token 延迟带来的体验。",
     ["正确", "错误"], "A", "流式让用户更快看到内容，感知等待显著降低。", "入门"),

    ("评估与安全", "single", "构建最小可行评估集时，最关键的是？",
     ["题目数量达到一万条", "覆盖真实使用分布且答案可自动判定",
      "全部使用学术基准", "只由开发者自己出题"],
     "B", "分布代表性与可自动判定是评估能进入迭代循环的前提。", "进阶"),
    ("评估与安全", "single", "抑制幻觉最有效的工程手段是？",
     ["提高 temperature", "允许模型回答「资料中没有」并强制引用来源",
      "增加生成长度", "更换更礼貌的提示词"],
     "B", "把「不知道」变成可接受的输出，是抑制编造的第一道闸门。", "进阶"),
    ("评估与安全", "multi", "红队测试的常见攻击手法包括？",
     ["角色扮演诱导", "编码混淆绕过关键词", "多轮对话逐步渗透", "随机丢弃训练数据"],
     "A,B,C", "丢训练数据属于训练侧问题，不是越狱攻击手法。", "高阶"),
    ("评估与安全", "single", "高风险领域（医疗/法律/金融）上线生成式功能的必要动作是？",
     ["完全禁止使用", "加入免责声明与人工复核入口并留存追溯信息",
      "只对内部员工开放", "关闭日志以保护隐私"],
     "B", "合规提示 + 人工复核 + 可追溯是落地的基本门槛。", "高阶"),
    ("评估与安全", "judge", "用户输入是否回流用于训练，平台应明确告知并提供关闭选项。",
     ["正确", "错误"], "A", "这是数据合规的基本要求。", "进阶"),
]

NEWS = [
    ("OpenAI 发布新一代推理模型，数学与代码基准显著提升", "新模型在多项推理基准上取得领先，重点强化了多步推理与工具调用能力，同时公布了新的对齐方案。",
     "大模型", "OpenAI,推理模型,基准", "官方博客", 86),
    ("国内首个大模型备案新规落地，明确生成内容标识要求", "监管细则明确了生成合成内容的标识、追溯与平台责任划分，对教育类 AI 应用提出了更高要求。",
     "政策", "监管,备案,合规", "监管公告", 74),
    ("新一代国产 AI 芯片量产，单卡显存大幅提升", "新芯片面向训练场景，显存与互联带宽明显增强，有望缓解大模型训练算力瓶颈。",
     "硬件", "芯片,算力,训练", "产业新闻", 68),
    ("AI 编程助手渗透率突破关键节点，研发效率提升明显", "多家企业披露内部数据显示，AI 辅助编码已覆盖大部分日常开发任务，代码评审方式随之改变。",
     "应用", "编程助手,研发效率", "行业报告", 62),
    ("研究团队披露新型提示词注入攻击，主流 Agent 产品受影响", "攻击者可通过网页内容劫持 Agent 行为，研究团队同时给出了检测与缓解建议。",
     "安全", "提示词注入,Agent,安全", "论文", 79),
    ("开源社区发布高效微调框架，消费级显卡可训练 7B 模型", "新框架结合 4bit 量化与 LoRA，显著降低了微调的显存门槛，社区反响热烈。",
     "大模型", "开源,LoRA,微调", "GitHub", 58),
    ("多模态大模型进入实用阶段，图文理解准确率再创新高", "新版本在文档理解、图表问答等任务上表现突出，为教育场景的智能答疑提供了更好基础。",
     "大模型", "多模态,文档理解", "官方发布", 71),
    ("AI 教育应用监管指引发布，强调学习过程可追溯", "指引要求面向未成年人的 AI 产品提供时长管理与内容过滤，并保留学习记录以备核查。",
     "政策", "教育,未成年人,指引", "监管公告", 55),
    ("推理成本一年下降一个数量级，应用层迎来爆发窗口", "算力优化与服务商竞争共同推动推理价格下降，中小企业部署 AI 应用的门槛明显降低。",
     "应用", "推理成本,应用落地", "行业分析", 66),
    ("新型向量数据库版本发布，检索性能大幅提升", "新版本在十亿级向量规模下保持毫秒级响应，并原生支持混合检索与重排序。",
     "应用", "向量数据库,RAG", "官方发布", 44),
    ("大模型对齐研究取得进展，偏好数据效率显著提高", "研究提出新的偏好学习方法，用更少的标注数据达到相近的对齐效果。",
     "大模型", "对齐,RLHF,DPO", "论文", 52),
    ("数据中心液冷方案加速普及，能耗指标持续改善", "随着训练集群功率密度上升，液冷成为新建数据中心的默认选项，PUE 指标明显下降。",
     "硬件", "数据中心,液冷,能耗", "产业新闻", 38),
]

COURSES = [
    ("liyuan", "大模型原理 30 讲：从 Transformer 到对齐", "大模型基础",
     "系统拆解 Transformer、注意力、预训练、SFT 与 RLHF，配套 30 讲视频与课后测验，适合零基础转 AI 方向的同学。",
     199.0, 399.0, "recorded", 0,
     [("第一章 · 架构基础", [("Transformer 全景速览", "video", 1, 22),
                            ("自注意力机制推导", "video", 0, 35),
                            ("位置编码与长文本", "video", 0, 28)]),
      ("第二章 · 训练范式", [("预训练任务设计", "video", 0, 31),
                            ("SFT 数据构造实战", "video", 0, 40),
                            ("RLHF 与 DPO 对比", "video", 0, 33)]),
      ("第三章 · 阶段测验", [("原理综合测验", "quiz", 0, 20)])]),
    ("wangxue", "提示词工程实战：从入门到稳定产出", "提示词工程",
     "不讲玄学，只讲可复现的方法：四要素模板、Few-shot、CoT、结构化输出与注入防御，含 20 个可直接复用的提示词模板。",
     129.0, 259.0, "recorded", 0,
     [("第一章 · 基础心法", [("提示词四要素", "video", 1, 18),
                            ("常见误区与反例", "video", 0, 21)]),
      ("第二章 · 进阶技巧", [("Few-shot 与思维链", "video", 0, 27),
                            ("结构化输出与自修复", "video", 0, 25),
                            ("提示词注入防御", "video", 0, 24)]),
      ("第三章 · 模板库", [("20 个高频场景模板", "doc", 0, 15)])]),
    ("liyuan", "LoRA 微调实战：一张显卡跑通全流程", "微调实战",
     "从数据清洗、LoRA 配置、训练监控到效果评估的完整闭环，附可运行代码与踩坑清单。",
     299.0, 599.0, "recorded", 0,
     [("第一章 · 准备", [("环境与显存估算", "video", 1, 26),
                        ("指令数据清洗", "video", 0, 30)]),
      ("第二章 · 训练", [("LoRA 参数怎么调", "video", 0, 34),
                        ("训练监控与止损", "video", 0, 29)]),
      ("第三章 · 评估与部署", [("效果评估与回归测试", "video", 0, 31),
                              ("权重合并与部署", "video", 0, 24)])]),
    ("wangxue", "RAG 企业级落地：检索、重排与评估", "AI 应用开发",
     "用真实文档搭建一套可用的知识库问答，重点解决「检索不到」和「检索到但不用」两大顽疾。",
     249.0, 449.0, "recorded", 0,
     [("第一章 · 检索基础", [("嵌入与相似度", "video", 1, 23),
                            ("切分策略实战", "video", 0, 26)]),
      ("第二章 · 提升精度", [("MMR 去冗与重排序", "video", 0, 32),
                            ("混合检索方案", "video", 0, 28)]),
      ("第三章 · 评估与迭代", [("检索指标怎么量化", "video", 0, 25)])]),
    ("liyuan", "AI Agent 开发：工具调用与流程编排", "AI 应用开发",
     "从 Function Calling 到多步 Agent 循环，讲清终止条件、错误恢复与成本控制。",
     219.0, 399.0, "recorded", 0,
     [("第一章 · 工具调用", [("Function Calling 设计", "video", 1, 24),
                            ("参数 Schema 与校验", "video", 0, 22)]),
      ("第二章 · Agent 循环", [("ReAct 与终止条件", "video", 0, 30),
                              ("错误恢复与重试", "video", 0, 26)])]),
    ("wangxue", "AI 学习路径规划（免费公开课）", "职业发展",
     "面向零基础与转行同学：三个月学习路线、必备工具清单、以及如何做出能写进简历的项目。",
     0.0, 0.0, "text", 0,
     [("第一章 · 路线图", [("三个月学习路线", "doc", 1, 12),
                          ("必备工具与资源", "doc", 0, 10)]),
      ("第二章 · 作品集", [("如何做出可展示的项目", "doc", 0, 15)])]),
]

LIVES = [
    ("liyuan", "大模型原理答疑专场：注意力到底怎么算", "本周答疑：把注意力矩阵真正动手算一遍，现场回答学员提问。",
     0, "free", 0, 2, 40),
    ("wangxue", "提示词工程公开课：让你的输出稳定下来", "公开课：结构化输出 + 自修复循环，现场演示三个真实场景。",
     0, "free", 3, 3, 55),
    ("liyuan", "LoRA 微调实战直播：从 0 跑通一次训练", "带练直播：现场配置 LoRA、启动训练、观察 loss 曲线。",
     99, "paid", 1, 5, 90),
    ("wangxue", "RAG 系统调优实战：把命中率提上去", "实战直播：现场对一套失败案例做检索诊断与重排优化。",
     0, "free", 6, 4, 60),
]

POSTS = [
    ("fangyuan", "从后端转 AI 应用开发，三个月我踩过的坑", "综合讨论",
     "转方向三个月，最大的体会是：**别一上来就啃微调**。\n\n"
     "我一开始花了半个月研究 LoRA，结果发现我的业务场景根本用不上——提示词 + RAG 就够了。\n\n"
     "整理几个具体建议：\n\n1. 先把提示词写到极致，再考虑别的\n2. RAG 是性价比最高的技能，学会切分和重排就有明显提升\n3. 一定要建立评估集，否则你根本不知道自己有没有变好\n\n"
     "现在我在做一个内部知识库问答，命中率从 40% 提到了 78%，靠的就是「重排序 + 引用约束」。有问题欢迎评论区聊～", ["转行", "经验"]),
    ("liyuan", "【精华】为什么你的提示词总是不稳定", "提示词工程",
     "回答过太多这个问题了，统一说下。\n\n"
     "**90% 的不稳定来自三个原因**：\n\n- 约束没写清楚（长度、格式、不知道时怎么办）\n- 没有给示例（你以为描述清楚了，其实没有）\n- 让模型自由发挥格式，然后你自己用正则去猜\n\n"
     "第三条最致命。输出格式应该由 Schema 约束，而不是靠模型自觉。\n\n"
     "`不要输出任何解释，只返回 JSON` 这句话，能省掉你一半的解析代码。", ["提示词", "干货"]),
    ("xiaoai", "打卡第 30 天：注意力机制终于看懂了", "大模型基础",
     "今天终于把 QKV 想明白了。\n\n"
     "打个比方：Q 是你在搜索框输入的关键词，K 是每篇文章的标题，V 是文章内容。\n"
     "先用 Q 和每个 K 算相似度（谁跟我最相关），softmax 之后当成权重，最后对 V 加权求和——就是你「记住」的内容。\n\n"
     "不知道这个理解对不对，@liyuan 老师能点评一下吗？", ["打卡", "学习笔记"]),
    ("azhe", "RAG 检索不到内容，排查了两天的结论", "AI 应用开发",
     "记录一次排障。现象：知识库明明有答案，模型就是说没有。\n\n"
     "排查过程：\n"
     "- 先看召回：Top-5 里确实没有正确段落 ❌\n"
     "- 怀疑切分：把 2000 字的块改成按标题切，命中率提升明显 ✅\n"
     "- 再看嵌入模型：换中文优化过的模型，又提升一档 ✅\n"
     "- 最后加重排序：Top-3 命中率从 62% 到 81% ✅\n\n"
     "结论：**先定位是检索问题还是生成问题**，别一上来就改提示词。", ["RAG", "排障"]),
    ("chenmo", "关于微调的困惑：数据和 epoch 到底怎么定", "微调实战",
     "看了一些教程，有人说 3 个 epoch，有人说 10 个。到底听谁的？\n\n"
     "我自己的数据大概 3000 条，7B 模型，LoRA r=8。求 @liyuan 老师指点。", ["微调", "求助"]),
    ("wangxue", "分享一套我常用的提示词模板结构", "提示词工程",
     "我自己的模板长这样，用了两年基本没变过：\n\n"
     "```\n角色：你是……\n任务：请……\n约束：\n- 输出格式：……\n- 长度：……\n- 资料不足时：明确回答「资料中未提及」\n示例：\n输入：……\n输出：……\n```\n\n"
     "关键是最后那条——**允许它说不知道**，幻觉能少一大半。", ["模板", "干货"]),
    ("fangyuan", "建了个 AI 学习小组，欢迎一起打卡", "综合讨论",
     "一个人学容易放弃，想组个小组每天打卡。\n\n"
     "形式：每天一个知识点 + 一道题，晚上在讨论区发学习笔记。\n"
     "有兴趣的回复 +1，满 5 个人我就建起来。", ["打卡", "招募"]),
    ("xiaoai", "提问：练测里的错题本怎么复习最有效", "综合讨论",
     "我的错题本已经攒了 20 多道了，感觉越攒越多……\n\n"
     "大家是怎么复习错题的？是全部重做一遍，还是只看解析？", ["学习方法"]),
    ("azhe", "把课程里的 LoRA 代码跑通了，分享踩坑记录", "微调实战",
     "跑通第一次 LoRA 训练，记录三个坑：\n\n"
     "1. `target_modules` 名字写错，训练静默不生效（loss 几乎不动）\n"
     "2. 显存不够，把 `batch_size` 降到 1 再开梯度累积\n"
     "3. 中文数据没做长度过滤，超长样本直接把显存吃满\n\n"
     "附上我用的配置，供参考。", ["LoRA", "踩坑"]),
]

FILES = [
    ("提示词模板库.md", "课件", "提示词,模板",
     "# 提示词模板库\n\n## 1. 结构化输出\n角色：数据抽取助手\n任务：从给定文本中抽取字段\n约束：只输出 JSON，不要解释\n\n## 2. 摘要\n...\n", "public"),
    ("LoRA-训练配置.yaml", "代码", "LoRA,配置",
     "r: 8\nlora_alpha: 16\nlora_dropout: 0.05\ntarget_modules:\n  - q_proj\n  - v_proj\nlearning_rate: 2e-4\nnum_train_epochs: 2\n", "public"),
    ("AI 学习路线图.txt", "其他", "路线图,学习",
     "第 1 周：大模型基础（Transformer / 注意力）\n第 2 周：提示词工程\n第 3 周：RAG 检索增强\n第 4 周：微调实战\n第 5 周：Agent 开发\n", "login"),
    ("RAG 排障清单.md", "论文", "RAG,排障",
     "# RAG 排障清单\n\n- [ ] Top-K 是否过小\n- [ ] 切分粒度是否合理\n- [ ] 嵌入模型是否支持中文\n- [ ] 是否做了重排序\n- [ ] 提示词是否要求引用来源\n", "public"),
]


# ============================ 执行 ============================
def seed_all(force: bool = False) -> dict:
    db.init_db()
    if is_seeded() and not force:
        return {"skipped": True}
    stat: dict = {}
    ids = seed_users()
    stat["users"] = len(ids)

    # 知识点
    if int(db.scalar("SELECT COUNT(*) FROM knowledge", (), 0)) == 0:
        for module, title, summary, body, formula, code, diff in KNOWLEDGE:
            knowledge.add_knowledge(module, title, summary, body, formula, code, diff)
    stat["knowledge"] = int(db.scalar("SELECT COUNT(*) FROM knowledge", (), 0))

    # 题库
    if int(db.scalar("SELECT COUNT(*) FROM questions", (), 0)) == 0:
        for module, qtype, stem, options, answer, analysis, diff in QUESTIONS:
            quiz.add_question(module, qtype, stem, options, answer, analysis, diff)
    stat["questions"] = int(db.scalar("SELECT COUNT(*) FROM questions", (), 0))

    # 新闻
    if int(db.scalar("SELECT COUNT(*) FROM news", (), 0)) == 0:
        for i, (title, summary, cat, tags, source, weight) in enumerate(NEWS):
            pub = _fmt(datetime.now() - timedelta(days=i * 9 + 2))
            nid = news.create_news(
                title, summary,
                content=(f"{summary}\n\n【要点】\n"
                         f"· 该进展标志着 {cat} 方向的重要变化，值得持续关注。\n"
                         f"· 对学习者的启示：关注其背后的方法而非单一结论。\n"
                         f"· 建议结合本站「知识点讲解 · {cat if cat != '政策' else '评估与安全'}」模块一起理解。\n"),
                category=cat, tags=tags, source=source,
                url=f"https://example.com/news/{i+1}",
                image="", publish_time=pub, status="published")
            db.execute("UPDATE news SET views=?, likes=? WHERE id=?", (weight * 37, weight // 3, nid))
        # 两条待审核（模拟自动抓取后的人工审核队列）
        for tpl in auto_fetch_templates():
            news.create_news(tpl["title"], tpl["summary"], tpl["content"],
                             tpl["category"], tpl["tags"], tpl["source"],
                             tpl["url"], "", _fmt(datetime.now()), "pending")
    stat["news"] = int(db.scalar("SELECT COUNT(*) FROM news", (), 0))

    # 课程
    if int(db.scalar("SELECT COUNT(*) FROM courses", (), 0)) == 0:
        for uname, title, cat, intro, price, orig, ctype, vdays, chapters in COURSES:
            cid = courses.create_course(ids[uname], title, intro, cat, price, orig, ctype,
                                        cover="", tags=cat, validity_days=vdays, status="on")
            for ch_title, lessons in chapters:
                ch_id = courses.add_chapter(cid, ch_title)
                for l_title, ltype, free, dur in lessons:
                    courses.add_lesson(cid, ch_id, l_title, ltype,
                                       content=f"《{title}》· {l_title}", duration=dur * 60,
                                       is_free=bool(free))
            # 评价打底
            for uname_r, rating, text in [("fangyuan", 5, "讲得很清楚，终于把注意力搞懂了。"),
                                          ("xiaoai", 5, "配套测验很实用，能查漏补缺。"),
                                          ("azhe", 4, "内容扎实，希望多加一些实战案例。")]:
                db.execute("INSERT INTO course_reviews(course_id,user_id,rating,content,created_at) "
                           "VALUES(?,?,?,?,?)", (cid, ids[uname_r], rating, text, db.now_str()))
            courses._recalc_rating(cid)
            db.execute("UPDATE courses SET sales=? WHERE id=?", (8 + (cid * 3) % 40, cid))
    stat["courses"] = int(db.scalar("SELECT COUNT(*) FROM courses", (), 0))

    # 直播
    if int(db.scalar("SELECT COUNT(*) FROM lives", (), 0)) == 0:
        all_courses = courses.list_courses(limit=50)
        for i, (uname, title, intro, price, access, day_offset, hours, dur) in enumerate(LIVES):
            start = datetime.now() + timedelta(days=day_offset, hours=hours)
            cid = all_courses[i % len(all_courses)]["id"] if all_courses else 0
            lid = live.create_live(ids[uname], title, _fmt(start), intro, price, access, cid)
            db.execute("UPDATE lives SET status=? WHERE id=?",
                       ("live" if day_offset in (1,) else ("replay" if day_offset <= 0 else "upcoming"), lid))
            # 预约
            for uname_r in ("fangyuan", "xiaoai", "azhe", "chenmo"):
                live.reserve(lid, ids[uname_r])
            # 聊天记录
            for uname_c, msg in [("xiaoai", "老师讲得好清楚！"), ("azhe", "这个例子太形象了"),
                                 ("liyuan", "有问题随时打在公屏上～"), ("fangyuan", "+1，学到了")]:
                live.send_chat(lid, ids[uname_c], msg)
            # 互动
            live.create_interaction(lid, "poll", "你觉得哪一部分最难？",
                                    ["注意力机制", "微调参数", "RAG 调优", "评估方法"])
            if access == "free":
                db.execute("UPDATE lives SET online_count=? WHERE id=?", (6 + i * 3, lid))
            else:
                db.execute("UPDATE lives SET online_count=? WHERE id=?", (2 + i, lid))
    stat["lives"] = int(db.scalar("SELECT COUNT(*) FROM lives", (), 0))

    # 帖子
    if int(db.scalar("SELECT COUNT(*) FROM posts", (), 0)) == 0:
        for uname, title, topic, content, tags in POSTS:
            pid = forum.create_post(ids[uname], title, content, topic, ",".join(tags))
            db.execute("UPDATE posts SET likes=? WHERE id=?", (7 + (pid * 5) % 40, pid))
    stat["posts"] = int(db.scalar("SELECT COUNT(*) FROM posts", (), 0))
    # 评论 + 点赞
    all_posts = db.query("SELECT id FROM posts ORDER BY id")
    comment_pool = [
        (ids["xiaoai"], "写得太好了，收藏了！"),
        (ids["azhe"], "同感，我也是卡在这一步很久。"),
        (ids["liyuan"], "补充一点：建议同时准备好评估集，否则很难量化提升。"),
        (ids["chenmo"], "请问有推荐的资料吗？"),
        (ids["wangxue"], "这个思路可以推广到很多场景。"),
    ]
    for p in all_posts:
        for j, (uid_c, text) in enumerate(comment_pool[: 2 + (p["id"] % 3)]):
            forum.add_comment(p["id"], uid_c, text)
        for uname_l in ("xiaoai", "azhe", "chenmo", "wangxue"):
            db.execute("INSERT OR IGNORE INTO post_likes(user_id,post_id,created_at) VALUES(?,?,?)",
                       (ids[uname_l], p["id"], db.now_str()))
    # 置顶与加精
    top = db.query("SELECT id FROM posts ORDER BY likes DESC LIMIT 1")
    if top:
        forum.set_pin(top[0]["id"], True)
    essence = db.query("SELECT id FROM posts WHERE title LIKE '%精华%' LIMIT 1")
    if essence:
        forum.set_essence(essence[0]["id"], True)

    # 文件
    if int(db.scalar("SELECT COUNT(*) FROM files", (), 0)) == 0:
        owners = ["fangyuan", "liyuan", "wangxue", "azhe"]
        for i, (fname, cat, tags, text, vis) in enumerate(FILES):
            files.save_upload(ids[owners[i % len(owners)]], fname, text.encode("utf-8"), cat, tags, vis)
    stat["files"] = int(db.scalar("SELECT COUNT(*) FROM files", (), 0))

    # 商品 / 优惠券 / 订单
    commerce.sync_course_products()
    for code, ctype, value, mina, days, uses in [
        ("WELCOME10", "full_reduce", 10.0, 50.0, 90, 1000),
        ("NEW20", "newcomer", 20.0, 100.0, 60, 500),
        ("VIP88", "discount", 0.88, 200.0, 30, 300),
    ]:
        cpid = commerce.create_coupon(code, ctype, value, mina, days, uses)
        commerce.grant_coupon(ids["fangyuan"], cpid)
        commerce.grant_coupon(ids["azhe"], cpid)
    stat["coupons"] = int(db.scalar("SELECT COUNT(*) FROM coupons", (), 0))

    if int(db.scalar("SELECT COUNT(*) FROM orders", (), 0)) == 0:
        # 方圆：已购两门课（走完整下单 + 支付回调链路）
        for uname, ctitle in [("fangyuan", "大模型原理 30 讲：从 Transformer 到对齐"),
                              ("fangyuan", "提示词工程实战：从入门到稳定产出"),
                              ("azhe", "LoRA 微调实战：一张显卡跑通全流程")]:
            c = db.query_one("SELECT * FROM courses WHERE title=?", (ctitle,))
            if not c:
                continue
            p = db.query_one("SELECT * FROM products WHERE ptype='course' AND ref_id=?", (c["id"],))
            if not p:
                continue
            no = commerce.create_order(ids[uname], [p["id"]], pay_method="wechat")
            commerce.pay_order(no, "wechat",
                               commerce.sign_payload({"order_no": no, "amount": p["price"],
                                                      "method": "wechat"}))
        # 一笔待支付订单，用于演示订单状态
        p = db.query_one("SELECT * FROM products WHERE ptype='course' LIMIT 1")
        if p:
            commerce.create_order(ids["chenmo"], [p["id"]], pay_method="")
    stat["orders"] = int(db.scalar("SELECT COUNT(*) FROM orders", (), 0))

    # 学习进度（方圆）
    e = db.query_one("SELECT * FROM enrollments WHERE user_id=? LIMIT 1", (ids["fangyuan"],))
    if e:
        ls = courses.lessons(e["course_id"])
        for l in ls[: max(1, len(ls) // 2)]:
            courses.mark_lesson(ids["fangyuan"], l["id"], True)

    # 测评记录 / 错题本
    if int(db.scalar("SELECT COUNT(*) FROM quiz_records", (), 0)) == 0:
        for uname, module in [("fangyuan", "大模型基础"), ("xiaoai", "提示词工程"), ("azhe", "RAG 与向量检索")]:
            qs = quiz.draw(module, 6)
            if not qs:
                continue
            answers = {}
            for i, q in enumerate(qs):
                answers[str(q["id"])] = q["answers"][0] if i % 3 else "A"
            quiz.submit(ids[uname], "practice", module, qs, answers, duration=420)

    # 通知
    notify.push(ids["fangyuan"], "system", "欢迎来到「BGL 的 AI 学习」！建议从「知识点讲解 → 大模型基础」开始。",
                link="knowledge")
    notify.push(ids["fangyuan"], "order", "你购买的课程已开通，快去「我的学习」继续吧。", link="my")

    # 访问日志与设置
    auth.log(ids["admin"], "admin", "seed", "初始化演示数据")
    db.set_setting("platform_name", "BGL 的 AI 学习")
    db.set_setting("max_users", auth.MAX_USERS)
    db.set_setting("refund_watch_limit", commerce.REFUND_WATCH_LIMIT)
    db.set_setting("seeded_at", db.now_str())
    return stat


def auto_fetch_templates() -> list:
    """模拟「定时抓取 → 待人工审核」的新闻条目。"""
    return [
        {"title": "某高校开设大模型应用微专业，课程覆盖 RAG 与 Agent",
         "summary": "课程面向本科高年级与研究生，强调动手实践与项目交付，首批名额迅速报满。",
         "content": "课程设置包括大模型基础、提示词工程、RAG 系统与 Agent 开发四个模块，"
                    "考核方式为项目制，要求学生独立完成一个可演示的 AI 应用。",
         "category": "应用", "tags": "教育,课程,实践", "source": "自动抓取", "url": "https://example.com/auto/1"},
        {"title": "开源社区发布大模型评测集，覆盖中文推理与安全",
         "summary": "新评测集包含推理、代码、安全三类任务，强调中文场景下的真实分布。",
         "content": "评测集公开了全部题目与评分脚本，并提供了基线模型的成绩，便于横向对比。",
         "category": "大模型", "tags": "评测,开源,中文", "source": "自动抓取", "url": "https://example.com/auto/2"},
    ]


def reset_and_seed() -> dict:
    """重置数据库并重新灌入演示数据（管理员后台一键重置）。"""
    db.reset_db()
    return seed_all(force=True)
