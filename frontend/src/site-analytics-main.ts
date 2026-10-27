import { createApp } from "vue";
import { createPinia } from "pinia";
import SiteAnalyticsApp from "./SiteAnalyticsApp.vue";

const app = createApp(SiteAnalyticsApp);
app.use(createPinia());
app.mount("#app");
