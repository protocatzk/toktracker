import { createApp } from "vue";
import { createPinia } from "pinia";
import LoginApp from "./LoginApp.vue";

const app = createApp(LoginApp);
app.use(createPinia());
app.mount("#app");
