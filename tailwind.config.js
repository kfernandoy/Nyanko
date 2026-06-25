/** @type {import('tailwindcss').Config} */
// const plugin = require('tailwindcss/plugin')
const colors = require('tailwindcss/colors')

module.exports = {
  content: [
    "./src/**/*.{html,js}",
    "./node_modules/tw-elements/dist/js/**/*.js",
  ],
    theme: {
      extend: {
        scrollbar: {
          width: '12px', // Ancho de la scrollbar
          track: colors.gray[100],
          thumb: colors.purple[600],
        },
      },
    },
  plugins: [
    require("daisyui"),
    require("tw-elements/dist/plugin.cjs"),
    require('@tailwindcss/typography'),
    require("@tailwindcss/forms"),
    require('@tailwindcss/aspect-ratio'),
    require('@tailwindcss/line-clamp'),
    require('@tailwindcss/container-queries'),
    require('tailwind-scrollbar'),
  ]
};