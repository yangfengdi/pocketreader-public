(function () {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  if (document.querySelector(".needs-refresh")) {
    scheduleSoftRefresh();
  }

  document.querySelectorAll("[data-import-tabs]").forEach(function (tabs) {
    tabs.querySelectorAll("[data-target]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.classList.contains("active") ? "true" : "false");
      button.addEventListener("click", function () {
        var targetId = button.dataset.target;
        tabs.querySelectorAll("[data-target]").forEach(function (other) {
          var selected = other === button;
          other.classList.toggle("active", selected);
          other.setAttribute("aria-pressed", selected ? "true" : "false");
        });
        document.querySelectorAll(".import-panel").forEach(function (panel) {
          panel.classList.toggle("active", panel.id === targetId);
        });
      });
    });
  });

  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector("button[type='submit']");
      if (button) {
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = "处理中";
      }
    });
  });

  var copyFeedButton = document.querySelector("[data-copy-feed]");
  var copyFeedSource = document.querySelector("[data-copy-source]");
  if (copyFeedButton && copyFeedSource) {
    copyFeedButton.addEventListener("click", function () {
      navigator.clipboard.writeText(copyFeedSource.value).then(function () {
        copyFeedButton.textContent = "已复制";
        setTimeout(function () {
          copyFeedButton.textContent = "复制订阅地址";
        }, 1800);
      }).catch(function () {
        copyFeedSource.select();
        copyFeedButton.textContent = "请手动复制";
      });
    });
  }

  var player = document.querySelector(".player");
  if (!player) {
    return;
  }

  var audio = player.querySelector("audio");
  var itemId = player.dataset.itemId;
  var start = Number(player.dataset.start || 0);
  var nextUrl = player.dataset.nextUrl;
  var lastSentAt = 0;

  audio.addEventListener("loadedmetadata", function () {
    if (start > 0 && start < audio.duration - 3) {
      audio.currentTime = start;
    }
  });

  player.querySelectorAll("[data-skip]").forEach(function (button) {
    button.addEventListener("click", function () {
      audio.currentTime = Math.max(0, audio.currentTime + Number(button.dataset.skip));
      sendEvent("seek");
    });
  });

  var rate = player.querySelector("[data-rate]");
  if (rate) {
    rate.addEventListener("change", function () {
      audio.playbackRate = Number(rate.value);
    });
  }

  var cacheButton = player.querySelector("[data-cache-audio]");
  if (cacheButton) {
    cacheButton.addEventListener("click", function () {
      if (!("caches" in window)) {
        cacheButton.textContent = "当前浏览器不支持缓存";
        return;
      }
      caches.open("pocketreader-audio-v1").then(function (cache) {
        return cache.add(audio.currentSrc || audio.src);
      }).then(function () {
        cacheButton.textContent = "已缓存";
      }).catch(function () {
        cacheButton.textContent = "缓存失败";
      });
    });
  }

  audio.addEventListener("play", function () {
    sendEvent("play");
  });

  audio.addEventListener("pause", function () {
    sendEvent("pause");
  });

  audio.addEventListener("timeupdate", function () {
    var now = Date.now();
    if (now - lastSentAt > 10000) {
      lastSentAt = now;
      sendEvent("progress");
    }
  });

  audio.addEventListener("ended", function () {
    sendEvent("ended").finally(function () {
      if (nextUrl) {
        window.location.href = nextUrl;
      }
    });
  });

  window.addEventListener("beforeunload", function () {
    navigator.sendBeacon(
      "/api/items/" + itemId + "/event",
      new Blob([JSON.stringify({ event: "progress", position: audio.currentTime || 0 })], {
        type: "application/json"
      })
    );
  });

  function sendEvent(eventName) {
    return fetch("/api/items/" + itemId + "/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: eventName,
        position: audio.currentTime || 0
      })
    }).catch(function () {});
  }

  function scheduleSoftRefresh() {
    var lastInteractionAt = Date.now();
    ["click", "input", "change", "focusin", "keydown", "touchstart"].forEach(function (eventName) {
      document.addEventListener(eventName, function () {
        lastInteractionAt = Date.now();
      }, { passive: true });
    });

    window.setTimeout(function refreshWhenIdle() {
      if (shouldDeferRefresh(lastInteractionAt)) {
        window.setTimeout(refreshWhenIdle, 5000);
        return;
      }
      window.location.reload();
    }, 8000);
  }

  function shouldDeferRefresh(lastInteractionAt) {
    if (document.hidden) {
      return false;
    }
    if (Date.now() - lastInteractionAt < 30000) {
      return true;
    }
    if (document.querySelector("details[open]")) {
      return true;
    }
    var active = document.activeElement;
    if (active && active.matches && active.matches("input, textarea, select, button, audio")) {
      return true;
    }
    var activeAudio = document.querySelector("audio");
    if (activeAudio && !activeAudio.paused) {
      return true;
    }
    return false;
  }
})();
