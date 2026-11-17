/** Design tokens for the web UI. Output is compiled to ../web/styles.css (no CDN: SEC-16, SEC-22). */
module.exports = {
  content: ["../web/*.html", "../web/*.js"],
  safelist: ["heat-0", "heat-1", "heat-2", "heat-3", "heat-4"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter"', "system-ui", "-apple-system", '"Segoe UI"', "Roboto", "sans-serif"],
      },
      colors: {
        brand: { 50: "#eff6ff", 100: "#dbeafe", 500: "#3b82f6", 600: "#2563eb", 700: "#1d4ed8", 900: "#1e3a8a" },
        pol: {
          neg: "#dc2626", "neg-bg": "#dc2626", "neg-fg": "#ffffff",
          neu: "#64748b", "neu-bg": "#475569", "neu-fg": "#ffffff",
          pos: "#16a34a", "pos-bg": "#16a34a", "pos-fg": "#ffffff",
        },
        warn: { bg: "#f59e0b", border: "#d97706", fg: "#ffffff" },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15,23,42,.06), 0 1px 3px rgba(15,23,42,.04)",
        pop: "0 4px 6px -1px rgba(15,23,42,.08), 0 2px 4px -2px rgba(15,23,42,.05)",
      },
      keyframes: {
        fadeUp: { "0%": { opacity: 0, transform: "translateY(6px)" }, "100%": { opacity: 1, transform: "none" } },
        pop: { "0%": { opacity: 0, transform: "scale(.85)" }, "60%": { transform: "scale(1.04)" }, "100%": { opacity: 1, transform: "none" } },
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-3px)" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        slide: { "0%": { left: "-30%" }, "100%": { left: "100%" } },
      },
      animation: { "fade-up": "fadeUp .35s cubic-bezier(.2,.8,.2,1) both", pop: "pop .45s cubic-bezier(.2,.8,.2,1) both", float: "float 3s ease-in-out infinite", shimmer: "shimmer 2.2s linear infinite", slide: "slide 1.4s linear infinite" },
    },
  },
};
