import type {
  ArticleCard,
  ArticleDetail,
  ArticleListResponse,
  FeaturedResponse,
  FeaturedSlot,
  ItemsResponse,
  Source,
  Topic,
} from "./home-data";

const sources: Source[] = [
  {
    id: "source-cn-public-safety",
    name: "中国警察网",
    slug: "china-police-news",
    region: "domestic",
    country_code: "CN",
    language: "zh",
    source_type: "media",
    topics: ["policing", "artificial-intelligence", "procurement-projects"],
  },
  {
    id: "source-cn-procurement",
    name: "政府采购网",
    slug: "government-procurement",
    region: "domestic",
    country_code: "CN",
    language: "zh",
    source_type: "government",
    topics: ["procurement-projects", "public-safety-tech"],
  },
  {
    id: "source-global-tech",
    name: "Public Safety Tech Review",
    slug: "public-safety-tech-review",
    region: "foreign",
    country_code: "US",
    language: "en",
    source_type: "media",
    topics: ["artificial-intelligence", "cybersecurity", "public-safety-tech"],
  },
  {
    id: "source-research-journal",
    name: "公共安全研究观察",
    slug: "public-safety-research",
    region: "domestic",
    country_code: "CN",
    language: "zh",
    source_type: "academic",
    topics: ["research", "policy-standards"],
  },
];

export const MOCK_TAXONOMY: ItemsResponse<Topic> = {
  items: [
    ["policing", "警务应用", "Policing"],
    ["artificial-intelligence", "AI 与大模型", "AI & LLMs"],
    ["public-safety-tech", "公共安全技术装备", "Public Safety Technology"],
    ["cybersecurity", "网络与数据安全", "Cybersecurity & Data"],
    ["policy-standards", "政策与标准", "Policy & Standards"],
    ["procurement-projects", "采购与项目", "Procurement & Projects"],
    ["research", "研究成果", "Research"],
  ].map(([slug, name_zh, name_en], index) => ({
    id: `topic-${index + 1}`,
    slug,
    name_zh,
    name_en,
    parent_id: null,
  })),
};

export const MOCK_SOURCES: ItemsResponse<Source> = { items: sources };

const fixtureRows = [
  {
    id: "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d001",
    title: "湖北天门：筹建公安大模型智能运算体系",
    source_title: "天门市推进公安大模型智能运算体系建设",
    source: sources[0],
    published_at: "2026-09-20T08:30:00Z",
    summary: "项目拟建设面向警务实战的大模型算力与应用支撑体系，探索智能研判、知识检索和基层业务协同。",
    topics: ["policing", "artificial-intelligence", "procurement-projects"],
    media_preview: {
      kind: "image",
      url: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=720&q=80",
      thumbnail_url: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=480&q=75",
      alt_text: "警务数据中心的数字化屏幕",
      caption: "警务智能化基础设施建设",
    },
    importance_score: 0.98,
    slot: "p0",
    zh_body: "湖北天门正筹建公安大模型智能运算体系。该体系计划整合算力资源、警务知识和业务工具，为信息研判、执法监督及基层警务提供智能辅助。相关建设仍处于方案推进阶段，具体建设内容以正式采购和项目公告为准。",
    source_body: "Tianmen is planning an intelligent computing system for public security large language models, intended to support operational analysis and frontline services.",
  },
  {
    id: "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d002",
    title: "浙江丽水：“丽警星系”形成大规模警务 AI Agent 生态",
    source_title: "丽水发布警务智能体应用阶段性进展",
    source: sources[0],
    published_at: "2026-09-19T03:20:00Z",
    summary: "当地围绕接处警、案事件研判和政务服务等场景持续扩展智能体应用，并强调由民警审核关键结论。",
    topics: ["policing", "artificial-intelligence"],
    media_preview: null,
    importance_score: 0.91,
    slot: "p1",
    zh_body: "浙江丽水介绍了“丽警星系”警务智能体应用的最新进展。相关应用围绕接处警辅助、信息查询、案事件分析和内部知识服务展开，并通过权限控制和人工复核保障实际使用。",
    source_body: "Lishui in Zhejiang has reported progress in a constellation of AI agents for police workflows.",
  },
  {
    id: "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d003",
    title: "上海浦东建设基于大模型的执法监督平台",
    source_title: "浦东新区推进执法监督数字化平台建设",
    source: sources[1],
    published_at: "2026-09-18T06:10:00Z",
    summary: "平台将围绕执法流程规范、文书质量检查与风险线索提示提供辅助能力，目标是提升监督工作的可追溯性。",
    topics: ["policing", "artificial-intelligence", "policy-standards"],
    media_preview: {
      kind: "image",
      url: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=720&q=80",
      thumbnail_url: null,
      alt_text: "执法监督工作资料与电脑",
      caption: null,
    },
    importance_score: 0.86,
    slot: "p2",
    zh_body: "上海浦东新区推进基于大模型的执法监督平台建设，探索对执法流程和文书进行智能辅助检查，并提示需要人工关注的风险线索。平台设计强调数据权限管理、审查留痕和人工判断。",
    source_body: "Pudong is developing a large-model-based platform to support oversight of administrative enforcement.",
  },
  {
    id: "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d004",
    title: "宝鸡公安展示 AI 智能体实战应用",
    source_title: "宝鸡公安交流人工智能辅助警务的实战案例",
    source: sources[0],
    published_at: "2026-09-17T10:00:00Z",
    summary: "案例展示了知识问答和多源信息整理等辅助场景，强调智能工具用于提效，业务决定仍由工作人员负责。",
    topics: ["policing", "artificial-intelligence", "public-safety-tech"],
    media_preview: null,
    importance_score: 0.82,
    slot: "p3",
    zh_body: "宝鸡公安展示了人工智能智能体在业务知识问答、多源信息整理和常见流程辅助中的应用。演示内容说明，模型输出用于提供参考，民警仍需结合原始材料独立核实。",
    source_body: null,
  },
  {
    id: "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d005",
    title: "公安部交管科学研究所采购大模型微调训练服务器",
    source_title: "公安部交通管理科学研究所服务器采购项目公告",
    source: sources[1],
    published_at: "2026-09-16T01:30:00Z",
    summary: "采购内容包含用于模型训练与推理的计算设备，具体规格、预算与交付要求以采购公告为准。",
    topics: ["procurement-projects", "artificial-intelligence"],
    media_preview: null,
    importance_score: 0.78,
    slot: "p4",
    zh_body: "公安部交通管理科学研究所发布大模型微调训练服务器采购信息。公告列明项目设备需求和采购流程，相关技术参数与预算应以正式文件及后续澄清为准。",
    source_body: null,
  },
  {
    id: "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d006",
    title: "无锡启动警务大模型综合应用项目采购",
    source_title: "无锡市警务大模型综合应用项目采购信息",
    source: sources[1],
    published_at: "2026-09-15T09:15:00Z",
    summary: "项目围绕警务知识服务和业务辅助应用进行采购，预算与服务范围需以正式招标文件为准。",
    topics: ["procurement-projects", "policing", "artificial-intelligence"],
    media_preview: null,
    importance_score: 0.75,
    slot: "p5",
    zh_body: "无锡启动警务大模型综合应用项目采购，计划采购相关软件、集成与技术服务。示例内容用于 Mock 预览，金额、采购范围和实施要求应以正式公告为准。",
    source_body: null,
  },
  {
    id: "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d007",
    title: "美国城市发布公共安全视频分析采购框架",
    source_title: "New procurement framework for public safety video analytics",
    source: sources[2],
    published_at: "2026-09-14T14:05:00Z",
    summary: "采购框架增加数据留存、访问审计和供应商评估要求，反映公共安全视频系统治理标准的变化。",
    topics: ["public-safety-tech", "policy-standards", "cybersecurity"],
    media_preview: {
      kind: "image",
      url: "https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=720&q=80",
      thumbnail_url: null,
      alt_text: "夜间城市街道与基础设施",
      caption: null,
    },
    importance_score: 0.72,
    slot: null,
    zh_body: null,
    source_body: null,
  },
  {
    id: "4ed2a8d4-efb7-4ce6-8a43-4ee36f27d008",
    title: "研究团队评估公共安全 AI 系统的人工复核机制",
    source_title: "Human review in public safety AI: a field evaluation",
    source: sources[3],
    published_at: "2026-09-13T07:45:00Z",
    summary: "一项研究比较了不同人工复核流程对告警准确性、处置时长和工作负荷的影响。",
    topics: ["research", "artificial-intelligence", "policy-standards"],
    media_preview: null,
    importance_score: 0.68,
    slot: null,
    zh_body: "研究团队通过现场评估比较公共安全 AI 系统中的不同人工复核流程，报告关注误报处置、决策可追溯性和一线人员工作负荷。研究结论仍需结合当地制度与系统部署条件理解。",
    source_body: "This field evaluation compares human review workflows for AI systems used in public safety settings.",
  },
];

function makeCard(row: (typeof fixtureRows)[number]): ArticleCard {
  return {
    id: row.id,
    title: row.title,
    source_title: row.source_title,
    published_at: row.published_at,
    first_seen_at: row.published_at,
    language: row.source.language,
    region: row.source.region,
    country_code: row.source.country_code,
    url: `https://example.com/articles/${row.id}`,
    source: row.source,
    importance_score: row.importance_score,
    processing_status: "complete",
    parse_status: "success",
    topics: row.topics,
    summary: row.summary,
    media_preview: row.media_preview,
  };
}

const cards = fixtureRows.map(makeCard);

export const MOCK_HOME_FEATURED: FeaturedResponse = {
  generated_at: "2026-09-20T09:00:00Z",
  window_policy: "24h_then_7d",
  items: fixtureRows
    .slice(0, 6)
    .map((row) => ({
      slot: row.slot as FeaturedSlot,
      article: makeCard(row),
      importance_score: row.importance_score,
    })),
};

export const MOCK_HOME_ARTICLES: ArticleListResponse = {
  items: cards,
  next_cursor: null,
  limit: 20,
};

export const MOCK_HOME_DATA = {
  featured: MOCK_HOME_FEATURED.items.map(({ article }) => article),
  articles: MOCK_HOME_ARTICLES.items,
  taxonomy: MOCK_TAXONOMY.items,
  sources: MOCK_SOURCES.items,
};

export const MOCK_ARTICLE_DETAILS: Record<string, ArticleDetail> =
  Object.fromEntries(
    fixtureRows.map((row) => {
      const card = makeCard(row);
      const detail: ArticleDetail = {
        ...card,
        author: null,
        source_body: row.source_body,
        zh_body: row.zh_body,
        fetched_at: row.published_at,
        quality_status: row.zh_body || row.source_body ? "available" : "unavailable",
        media: row.media_preview
          ? [
              {
                ...row.media_preview,
                position: 0,
                status: "available",
              },
            ]
          : [],
        comments: { available: false, count: 0, items: [] },
      };
      return [row.id, detail];
    }),
  );
