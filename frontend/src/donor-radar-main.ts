import { createApp } from "vue";
import { createPinia } from "pinia";
import DonorRadarApp from "./DonorRadarApp.vue";

const app = createApp(DonorRadarApp);
app.use(createPinia());
app.mount("#app");
