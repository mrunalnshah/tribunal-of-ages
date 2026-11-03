// Anonymous visit counts with PostHog: page views, clicks, and the events app.js names.
// Off until config.js has a project key, and always off on localhost. Nothing else in the site
// checks whether it's on: track() just does nothing then. What visitors type is never sent.
const analytics = (() => {
  const { key = "phc_wmKfGyUX9sMHA8muAh5ZySZGbjWi7Sr6BUFuzJVS3JLn", host = "https://us.i.posthog.com" } = window.TRIBUNAL_ANALYTICS || {};
  if (!key || ["localhost", "127.0.0.1"].includes(location.hostname)) return { track() {} };

  let ready = false;
  const waiting = []; // events tracked before the PostHog script has loaded
  const script = document.createElement("script");
  script.src = host.replace(".i.posthog.com", "-assets.i.posthog.com") + "/static/array.js";
  script.async = true;
  script.crossOrigin = "anonymous";
  script.addEventListener("load", () => {
    window.posthog.init(key, {
      api_host: host,
      persistence: "memory", // no cookies and no local storage, so there's nothing to consent to
      person_profiles: "identified_only", // nobody is ever identified, so every visitor is anonymous
      respect_dnt: true, // browsers that send Do Not Track aren't counted
      disable_session_recording: true, // no recordings of anyone's visit, whatever the settings say
    });
    ready = true;
    for (const [event, properties] of waiting.splice(0)) window.posthog.capture(event, properties);
  });
  document.head.append(script); // if an ad blocker stops it, events are simply dropped

  return {
    track(event, properties = {}) {
      if (ready) window.posthog.capture(event, properties);
      else if (waiting.length < 50) waiting.push([event, properties]);
    },
  };
})();