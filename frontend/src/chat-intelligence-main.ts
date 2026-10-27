import { createApp } from "vue";
import { createPinia } from "pinia";
import ChatIntelligenceApp from "./ChatIntelligenceApp.vue";

const app = createApp(ChatIntelligenceApp);
app.use(createPinia());
app.mount("#app");
