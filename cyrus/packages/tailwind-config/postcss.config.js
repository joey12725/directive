import tailwindcss from "@tailwindcss/postcss";

export default {
  plugins: [
    // Resolve the plugin from this shared package instead of the consuming app.
    tailwindcss(),
  ],
};
