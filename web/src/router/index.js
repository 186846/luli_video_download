import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import SummaryView from '../views/SummaryView.vue'
import { HOME_SEO, SUMMARY_DEFAULT_SEO, seoFromRoute } from '../composables/useSeo'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { seo: { ...HOME_SEO } },
    },
    {
      path: '/summary',
      name: 'summary',
      component: SummaryView,
      meta: { seo: { ...SUMMARY_DEFAULT_SEO } },
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

router.afterEach((to) => {
  seoFromRoute(to)
})

export default router
