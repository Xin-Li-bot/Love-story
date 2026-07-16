/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './static/app.js'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        roseGold: '#ad7480',
        roseDeep: '#895762',
        appleGray: '#f5f5f7'
      }
    }
  },
  plugins: []
};
