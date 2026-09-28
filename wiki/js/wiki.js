// ProxyProbe Wiki Interactive JS
document.addEventListener("DOMContentLoaded", () => {
  // Theme Toggle
  const themeToggleBtn = document.getElementById("themeToggle");
  const currentTheme = localStorage.getItem("wiki_theme") || "dark";
  document.documentElement.setAttribute("data-theme", currentTheme);
  updateThemeIcon(currentTheme);

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", () => {
      const activeTheme = document.documentElement.getAttribute("data-theme");
      const newTheme = activeTheme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", newTheme);
      localStorage.setItem("wiki_theme", newTheme);
      updateThemeIcon(newTheme);
    });
  }

  function updateThemeIcon(theme) {
    if (!themeToggleBtn) return;
    if (theme === "dark") {
      themeToggleBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"></circle>
          <line x1="12" y1="1" x2="12" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="23"></line>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
          <line x1="1" y1="12" x2="3" y2="12"></line>
          <line x1="21" y1="12" x2="23" y2="12"></line>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        </svg>
      `;
      themeToggleBtn.title = "切换至浅色模式";
    } else {
      themeToggleBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      `;
      themeToggleBtn.title = "切换至深色模式";
    }
  }

  // Mobile Sidebar Toggle
  const menuToggleBtn = document.getElementById("menuToggle");
  const sidebar = document.getElementById("sidebar");
  if (menuToggleBtn && sidebar) {
    menuToggleBtn.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });
    // Close sidebar on link click (mobile)
    document.querySelectorAll(".nav-link").forEach((link) => {
      link.addEventListener("click", () => {
        if (window.innerWidth <= 768) {
          sidebar.classList.remove("open");
        }
      });
    });
  }

  // Code Copy
  document.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const targetId = btn.getAttribute("data-target");
      const codeEl = targetId ? document.getElementById(targetId) : btn.closest(".code-block-wrapper")?.querySelector("code");
      if (!codeEl) return;
      const textToCopy = codeEl.innerText.trim();
      try {
        await navigator.clipboard.writeText(textToCopy);
        const originalText = btn.innerHTML;
        btn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span style="color:#10b981">已复制</span>
        `;
        setTimeout(() => {
          btn.innerHTML = originalText;
        }, 2000);
      } catch (err) {
        console.error("复制失败", err);
      }
    });
  });

  // Search Filter
  const searchInput = document.getElementById("wikiSearch");
  const navItems = document.querySelectorAll(".nav-item");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase().trim();
      navItems.forEach((item) => {
        const text = item.textContent.toLowerCase();
        if (text.includes(q)) {
          item.style.display = "block";
        } else {
          item.style.display = "none";
        }
      });
    });
  }

  // Scrollspy for Sidebar & TOC
  const sections = document.querySelectorAll(".doc-section");
  const navLinks = document.querySelectorAll(".nav-link");
  const tocLinks = document.querySelectorAll(".toc-link");

  function onScroll() {
    let currentId = "";
    sections.forEach((sec) => {
      const top = sec.offsetTop - 120;
      if (window.scrollY >= top) {
        currentId = sec.getAttribute("id");
      }
    });

    if (currentId) {
      navLinks.forEach((link) => {
        if (link.getAttribute("href") === `#${currentId}`) {
          link.classList.add("active");
        } else {
          link.classList.remove("active");
        }
      });
      tocLinks.forEach((link) => {
        if (link.getAttribute("href") === `#${currentId}`) {
          link.classList.add("active");
        } else {
          link.classList.remove("active");
        }
      });
    }
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
});
