(function () {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  if (document.querySelector(".needs-refresh")) {
    window.setTimeout(function () {
      window.location.reload();
    }, 5000);
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
})();

