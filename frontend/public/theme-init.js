// Applies the saved theme before the app bundle loads to avoid a light-mode flash.
// Kept as an external file because the CSP only allows scripts from 'self'.
(function () {
  try {
    var raw = localStorage.getItem('rooman_account_preferences');
    var theme = raw ? JSON.parse(raw).theme : 'light';
    var isDark =
      theme === 'dark' ||
      (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (isDark) document.documentElement.classList.add('dark');
  } catch (e) {
    /* storage unavailable - keep the default theme */
  }
})();
