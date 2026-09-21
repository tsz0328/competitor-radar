<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Top } from "@element-plus/icons-vue";
import Logo from "@/components/Logo.vue";
import { DOCS, DOC_LIST, type DocSection } from "@/data/docs";

/**
 * 文档页：隐私政策 / 服务条款 / 使用文档共用同一套骨架。
 * 正文都在 `@/data/docs`，这里只负责按路由 meta.doc 取出来渲染。
 */
const route = useRoute();
const router = useRouter();
/** 路由 meta.doc 决定渲染哪份；非法值退回使用文档 */
const doc = computed(() => DOCS[String(route.meta.doc)] ?? DOCS.guide);

/** 渲染块：把连续的 "- " 行合并成一个列表，其余按段落 */
interface Block {
  type: "p" | "ul";
  items: string[];
}
function blocksOf(section: DocSection): Block[] {
  const blocks: Block[] = [];
  for (const line of section.lines) {
    const isItem = line.startsWith("- ");
    const text = isItem ? line.slice(2) : line;
    const last = blocks[blocks.length - 1];
    if (isItem && last?.type === "ul") last.items.push(text);
    else blocks.push({ type: isItem ? "ul" : "p", items: [text] });
  }
  return blocks;
}

/** 目录锚点：用下标做 id，避免中文标题转 slug 的麻烦 */
const sectionId = (i: number) => `sec-${i}`;

function backHome() {
  router.push({ name: "Landing" });
}
function toTop() {
  window.scrollTo({ top: 0, behavior: "smooth" });
}
</script>

<template>
  <div class="docs-page">
    <header class="docs-header">
      <a class="docs-brand" @click="backHome">
        <Logo size="1.5em" />
        <span>竞品雷达</span>
      </a>
      <el-button class="docs-back" link @click="backHome">
        <el-icon><ArrowLeft /></el-icon>
        返回首页
      </el-button>
    </header>

    <!-- 文档切换：三份文档各有独立 URL，这里提供互相跳转（小屏也一直可见） -->
    <nav class="docs-switch">
      <router-link
        v-for="d in DOC_LIST"
        :key="d.key"
        class="docs-switch-item"
        :class="{ active: d.key === doc.key }"
        :to="{ name: d.route }"
        >{{ d.title }}</router-link
      >
    </nav>

    <div class="docs-layout">
      <!-- 左侧目录：小节够多才有意义 -->
      <aside v-if="doc.sections.length >= 4" class="docs-toc">
        <div class="docs-toc-title">{{ doc.title }}</div>
        <a
          v-for="(s, i) in doc.sections"
          :key="i"
          class="docs-toc-item"
          :href="`#${sectionId(i)}`"
          >{{ s.heading }}</a
        >
      </aside>

      <article class="docs-body">
        <h1 class="docs-title">{{ doc.title }}</h1>
        <div class="docs-updated">最后更新：{{ doc.updated }}</div>
        <p class="docs-summary">{{ doc.summary }}</p>

        <section
          v-for="(s, i) in doc.sections"
          :id="sectionId(i)"
          :key="s.heading"
          class="docs-section"
        >
          <h2 class="docs-heading">{{ s.heading }}</h2>
          <template v-for="(b, j) in blocksOf(s)" :key="j">
            <ul v-if="b.type === 'ul'" class="docs-list">
              <li v-for="(item, k) in b.items" :key="k">{{ item }}</li>
            </ul>
            <p v-else class="docs-text">{{ b.items[0] }}</p>
          </template>
        </section>

        <footer class="docs-footer">
          <span>© 2026 竞品雷达. All rights reserved.</span>
          <el-button class="docs-back" link @click="toTop">
            <el-icon><Top /></el-icon>
            回到顶部
          </el-button>
        </footer>
      </article>
    </div>
  </div>
</template>

<style scoped>
.docs-page {
  min-height: 100vh;
  background: var(--app-color-white);
  color: var(--app-color-black);
  padding-bottom: 6vh;
}

/* 顶部：品牌 + 返回 */
.docs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2vh 5vw;
  border-bottom: 1px solid
    color-mix(in oklch, var(--app-color-black) 10%, transparent);
}

.docs-brand {
  display: flex;
  align-items: center;
  gap: 0.6vw;
  font-size: 1.5vmax;
  font-weight: bold;
  cursor: pointer;
  transition: color 0.2s ease, transform 0.2s ease;
}

.docs-brand:hover {
  color: var(--app-color-blue);
  transform: scale(1.03);
}

.docs-back {
  font-size: 1.2vmax;
  color: var(--app-color-blue);
}

/* 文档切换标签：始终可见（小屏没有左侧目录时也能在文档之间走） */
.docs-switch {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 1vw;
  padding: 2.5vh 5vw 0;
}

.docs-switch-item {
  padding: 0.8vh 1.2vw;
  border-radius: 100vmax;
  font-size: 1.1vmax;
  text-decoration: none;
  color: var(--app-text-color-secondary);
  transition: color 0.2s ease, background-color 0.2s ease;
}

.docs-switch-item:hover {
  color: var(--app-color-blue);
  background: var(--app-color-blue-light-5);
}

/* 当前文档：跟登录/提交按钮同一套主色渐变，white 用 --el-color-white 避免暗色模式跟着翻转 */
.docs-switch-item.active {
  color: var(--el-color-white);
  background: linear-gradient(
    135deg,
    var(--app-color-blue-light-2),
    var(--app-color-purple)
  );
}

/* 正文 + 目录两栏 */
.docs-layout {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 3vw;
  padding: 3vh 5vw 0;
}

.docs-toc {
  position: sticky;
  top: 3vh;
  flex: 0 0 auto;
  max-width: 16vw;
  display: flex;
  flex-direction: column;
  gap: 1vh;
  padding: 1.5vh 1vw;
  border-radius: 1vmax;
  background: var(--app-color-blue-light-5);
  font-size: 1vmax;
}

.docs-toc-title {
  font-weight: bold;
  font-size: 1.1vmax;
  margin-bottom: 0.5vh;
}

.docs-toc-item {
  color: var(--app-text-color-secondary);
  text-decoration: none;
  line-height: 1.5;
  transition: color 0.15s ease;
}

.docs-toc-item:hover {
  color: var(--app-color-blue);
}

/* 控制单行长度，长文才好读 */
.docs-body {
  max-width: 68ch;
  font-size: 1.1vmax;
  line-height: 1.9;
}

.docs-title {
  margin: 0;
  font-size: 2.6vmax;
  background: linear-gradient(
    90deg,
    var(--app-color-purple),
    var(--app-color-blue-dark-3)
  );
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.docs-updated {
  margin-top: 1vh;
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.docs-summary {
  margin: 2.5vh 0 0;
  padding: 1.5vh 1.2vw;
  border-radius: 1vmax;
  background: var(--app-color-blue-light-5);
}

/* 目录锚点跳过来时，标题上方留点呼吸空间 */
.docs-section {
  margin-top: 3.5vh;
  scroll-margin-top: 2vh;
}

.docs-heading {
  margin: 0 0 1.2vh;
  font-size: 1.5vmax;
}

.docs-text {
  margin: 0 0 1vh;
}

.docs-list {
  margin: 0 0 1vh;
  padding-left: 1.4vw;
}

.docs-list li {
  margin-bottom: 0.4vh;
}

.docs-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1vw;
  margin-top: 6vh;
  padding-top: 2vh;
  border-top: 1px solid
    color-mix(in oklch, var(--app-color-black) 10%, transparent);
  font-size: 1vmax;
  color: var(--app-color-gray);
}

/* 窄屏放不下两栏：目录隐藏，正文占满 */
@media (max-width: 900px) {
  .docs-toc {
    display: none;
  }
}
</style>
