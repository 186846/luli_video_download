import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import SummaryView from '../views/SummaryView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/summary', name: 'summary', component: SummaryView },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
