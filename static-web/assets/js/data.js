/* 致壹 智能教育工作台 · 全局常量
   这里不存放任何演示数据，页面内容全部来自后端接口。 */
window.EDU = {
  brand: { name: "致壹", sub: "智能教育 · 本地运行" },
  teacher: { name: "", role: "教师", initials: "师" },
  student: { name: "", id: "", class: "", initials: "学" },

  courses: [],
  courseStats: {
    files: 0,
    lastPack: "—",
    tasks: 0,
    pending: 0,
    weak: "—",
    next: "—"
  },
  files: [],
  tasks: [],
  tutors: [],
  reviews: [],
  analytics: {
    kpi: [],
    points: [],
    errors: [],
    dims: [],
    supports: [],
    nextPlan: { title: "", items: [] }
  },
  lessonPacks: [],
  assets: []
};
