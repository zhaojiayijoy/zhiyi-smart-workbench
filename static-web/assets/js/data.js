/* 致壹 智能教育工作台 · 静态站示例数据
   所有内容用于静态演示，不连接任何真实模型或数据库。 */
window.EDU = {
  brand: { name: "致壹", sub: "智能教育 · 本地运行" },
  teacher: { name: "李老师", role: "教师", initials: "李" },
  student: { name: "陈思远", id: "S-017", class: "市场营销 24-1", initials: "陈" },

  courses: [
    {
      id: "c1",
      name: "消费者行为分析",
      class: "市场营销 24-1",
      classSize: 41,
      totalHours: 16,
      currentSession: 5,
      totalSessions: 8,
      textbook: "第 5 版",
      desc: "面向市场营销专业二年级学生的专业核心课，聚焦消费者决策过程与影响因素。",
      objectives: "知识目标：掌握消费者决策模型与影响因素\n能力目标：能独立完成消费者洞察报告\n素养目标：形成以数据为依据的分析习惯",
      key: "消费者决策模型、参照群体影响",
      diff: "情境因素对决策过程的干扰，学生难以区分因果",
      note: "每周三下午 3-4 节，机房授课",
      resourceCount: 6
    },
    {
      id: "c2",
      name: "市场营销基础",
      class: "市场营销 24-2",
      classSize: 38,
      totalHours: 12,
      currentSession: 8,
      totalSessions: 8,
      textbook: "第 3 版",
      desc: "面向一年级新生的入门课程，建立营销组合与市场调研的基本认知。",
      objectives: "知识目标：理解 4P 与 STP 理论\n能力目标：能完成简单的市场调研设计",
      key: "4P 营销组合",
      diff: "STP 理论与案例结合的迁移应用",
      note: "已完成全部课时，进入复习阶段",
      resourceCount: 4
    },
    {
      id: "c3",
      name: "数字营销实训",
      class: "电子商务 24-1",
      classSize: 32,
      totalHours: 20,
      currentSession: 2,
      totalSessions: 10,
      textbook: "校本实训手册 v2",
      desc: "以真实店铺数据为载体的项目制实训，覆盖投放、内容与转化分析。",
      objectives: "能力目标：能独立完成一次完整的投放复盘\n素养目标：具备数据合规意识",
      key: "投放 ROI 复盘",
      diff: "数据清洗与归因分析",
      note: "实训数据为脱敏样例",
      resourceCount: 5
    }
  ],

  courseStats: {
    files: 6,
    lastPack: "11-20 第 5 次课备课包",
    tasks: 3,
    pending: 4,
    weak: "参照群体影响",
    next: "第 6 次课：消费者态度与说服"
  },

  files: [
    { name: "消费者行为学（第5版）.pdf", ext: "PDF", size: "18.4 MB", kind: "教材", vis: "师生可见", chars: "126,480 字", date: "11-02 09:12" },
    { name: "课程标准-消费者行为分析.docx", ext: "DOCX", size: "86 KB", kind: "标准", vis: "教师可见", chars: "4,120 字", date: "11-02 09:15" },
    { name: "学情前测问卷.csv", ext: "CSV", size: "42 KB", kind: "表格", vis: "教师可见", chars: "48 行 × 9 列", date: "11-05 14:30" },
    { name: "本土品牌案例集.pdf", ext: "PDF", size: "6.2 MB", kind: "案例", vis: "师生可见", chars: "31,260 字", date: "11-08 10:02" },
    { name: "第5次课-参照群体.pptx", ext: "PPTX", size: "3.8 MB", kind: "课件", vis: "师生可见", chars: "24 页", date: "11-18 08:40" },
    { name: "作业模板-洞察报告.docx", ext: "DOCX", size: "120 KB", kind: "模板", vis: "师生可见", chars: "1,860 字", date: "11-19 16:12" }
  ],

  tasks: [
    { id: "t1", title: "双十一促销方案设计", status: "已发布", score: 100, date: "11-18 14:20", submitted: 32, total: 41 },
    { id: "t2", title: "消费者访谈与洞察报告", status: "已发布", score: 100, date: "11-12 09:05", submitted: 38, total: 41 },
    { id: "t3", title: "竞品价格带分析（Excel）", status: "草稿", score: 80, date: "11-20 16:40", submitted: 0, total: 0 }
  ],

  tutors: [
    { id: "q1", question: "为什么锚定效应会让原价显得更划算？", status: "已解决", point: "锚定效应", who: "陈思远", time: "11-21 20:14", visible: "师生可见" },
    { id: "q2", question: "参照群体和意见领袖在决策中有什么区别？", status: "AI引导中", point: "参照群体", who: "林小满", time: "11-21 19:02", visible: "师生可见" },
    { id: "q3", question: "消费者态度三成分模型怎么应用到广告设计？", status: "已解决", point: "消费者态度", who: "周予安", time: "11-20 15:48", visible: "师生可见" },
    { id: "q4", question: "损失厌恶能解释凑单行为吗？", status: "等待学生尝试", point: "损失厌恶", who: "陈思远", time: "11-20 10:31", visible: "教师可见" }
  ],

  reviews: [
    {
      id: "r1", student: "陈思远", anon: "S-017", file: "促销方案.docx", score: 86.5,
      status: "已发布", time: "11-21 21:40",
      dims: [
        { name: "理论应用", score: 27, max: 30, basis: "准确使用锚定效应与损失厌恶解释满减门槛设计", deduct: "参照群体部分仅一句带过", loc: "第 2 节，P3" },
        { name: "数据支撑", score: 22, max: 25, basis: "引用前测问卷中的价格敏感度分布", deduct: "未说明样本量，图表缺少单位", loc: "第 3 节，表 1" },
        { name: "方案可行性", score: 19, max: 25, basis: "给出三档满减与库存联动规则", deduct: "缺少成本测算，毛利风险未评估", loc: "第 4 节，P6" },
        { name: "表达规范", score: 18.5, max: 20, basis: "结构清晰，术语使用规范", deduct: "个别段落口语化", loc: "全文" }
      ],
      comment: "方案结构完整，理论应用到位。建议补充成本测算与样本说明，使结论更可信。",
      reason: ""
    },
    {
      id: "r2", student: "林小满", anon: "S-023", file: "定价策略分析.docx", score: 78,
      status: "待复核", time: "11-21 22:05",
      dims: [
        { name: "理论应用", score: 24, max: 30, basis: "使用价格弹性与心理定价策略", deduct: "弹性计算过程缺失", loc: "第 2 节，P2" },
        { name: "数据支撑", score: 20, max: 25, basis: "整理了竞品价格带", deduct: "数据来源未标注", loc: "第 3 节，表 2" },
        { name: "方案可行性", score: 19, max: 25, basis: "提出分层定价建议", deduct: "未考虑渠道返利", loc: "第 4 节" },
        { name: "表达规范", score: 15, max: 20, basis: "段落完整", deduct: "标题层级混乱，多处错别字", loc: "全文" }
      ],
      comment: "分析思路正确，但计算过程与数据来源需要补齐。",
      reason: "AI 对表达规范的扣分偏严，待教师确认。"
    },
    {
      id: "r3", student: "周予安", anon: "S-031", file: "渠道调研报告.docx", score: 91,
      status: "已发布", time: "11-20 18:26",
      dims: [
        { name: "理论应用", score: 29, max: 30, basis: "渠道冲突理论与案例高度契合", deduct: "—", loc: "第 1-2 节" },
        { name: "数据支撑", score: 23, max: 25, basis: "附访谈原始记录与编码表", deduct: "缺少定量交叉验证", loc: "附录 A" },
        { name: "方案可行性", score: 21, max: 25, basis: "给出三级渠道治理建议", deduct: "落地成本未估算", loc: "第 4 节" },
        { name: "表达规范", score: 18, max: 20, basis: "图表编号规范，引用完整", deduct: "参考文献格式不统一", loc: "文末" }
      ],
      comment: "调研扎实，访谈编码规范。补充成本估算后可作为班级范例。",
      reason: ""
    }
  ],

  analytics: {
    kpi: [
      { label: "答疑记录", value: "27", foot: "近 30 天，覆盖 3 个知识点", tone: "" },
      { label: "作业评审", value: "41", foot: "已发布 37 份，待复核 4 份", tone: "" },
      { label: "建议重点支持", value: "9 人", foot: "均分 < 60", tone: "warn" },
      { label: "建议提供拓展任务", value: "7 人", foot: "均分 ≥ 85", tone: "ok" }
    ],
    points: [
      { name: "参照群体影响", count: 11, ratio: 92 },
      { name: "锚定效应", count: 8, ratio: 66 },
      { name: "消费者态度", count: 5, ratio: 42 },
      { name: "损失厌恶", count: 3, ratio: 25 }
    ],
    errors: [
      { name: "概念混淆", ratio: 38, note: "参照群体与意见领袖边界不清" },
      { name: "因果倒置", ratio: 27, note: "把相关当因果，缺少控制变量" },
      { name: "数据误读", ratio: 21, note: "未区分百分比与百分点" },
      { name: "表达不规范", ratio: 14, note: "图表缺单位、引用不完整" }
    ],
    dims: [
      { name: "理论理解", score: 78 },
      { name: "数据分析", score: 71 },
      { name: "方案设计", score: 74 },
      { name: "表达规范", score: 82 },
      { name: "协作沟通", score: 76 }
    ],
    supports: [
      { who: "9 名学生", what: "均分低于 60，建议第 6 次课前安排 20 分钟概念澄清", tag: "重点支持" },
      { who: "7 名学生", what: "均分高于 85，建议追加开放型拓展任务（跨文化比较）", tag: "拓展" },
      { who: "全班", what: "数据误读占比 21%，建议增加图表阅读微练习", tag: "共性" }
    ],
    nextPlan: {
      title: "第 6 次课：消费者态度与说服",
      items: [
        "开场 10 分钟：用两道选择题快速澄清「参照群体 vs 意见领袖」",
        "新知 30 分钟：态度三成分模型 + 广告案例拆解",
        "练习 25 分钟：分组完成一则广告的态度成分标注",
        "收尾 10 分钟：发布分层作业（基础题 / 拓展题）"
      ]
    }
  },

  lessonPacks: [
    { title: "第 5 次课：参照群体与消费者决策", date: "11-20 16:22", model: "智谱 GLM-4", check: "双模型一致性 92%", status: "已审核" },
    { title: "第 4 次课：知觉与学习", date: "11-13 15:08", model: "智谱 GLM-4", check: "双模型一致性 88%", status: "已审核" },
    { title: "第 3 次课：动机与需要", date: "11-06 14:41", model: "智谱 GLM-4", check: "双模型一致性 90%", status: "已审核" }
  ],

  assets: [
    { name: "教案-参照群体.docx", meta: "4,120 字 · 45 分钟", tag: "教案" },
    { name: "课件-参照群体.pptx", meta: "22 页 · 含 3 个案例", tag: "PPT" },
    { name: "课堂练习-情境判断.docx", meta: "8 题 · 预计 15 分钟", tag: "练习" },
    { name: "答案与解析.docx", meta: "逐题解析 + 常见错误", tag: "答案" },
    { name: "评分量规.xlsx", meta: "4 维度 · 100 分", tag: "量规" }
  ]
};
