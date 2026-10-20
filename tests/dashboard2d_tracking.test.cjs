// Optional, network-free dashboard test: node --test tests/dashboard2d_tracking.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "visualization", "dashboard.js"),
  "utf8",
);

function fixture() {
  const elements = {};
  const document = {
    getElementById(id) {
      if (!elements[id]) {
        elements[id] = {
          textContent: "", className: "", disabled: false, style: {},
          classList: { add() {}, remove() {} },
          addEventListener() {},
        };
      }
      return elements[id];
    },
  };
  const window = {
    location: { protocol: "http:", host: "localhost" },
    dispatchEvent() {},
  };
  class FakeWebSocket { addEventListener() {} }
  class FakeCustomEvent {
    constructor(type, options) {
      this.type = type;
      this.detail = options.detail;
    }
  }
  const context = vm.createContext({
    document, window, WebSocket: FakeWebSocket,
    CustomEvent: FakeCustomEvent,
    fetch: () => new Promise(() => {}),
    setInterval() {}, setTimeout() {},
    Date, Number, Math, console,
  });
  vm.runInContext(source, context, { filename: "dashboard.js" });
  function call(name, value) {
    context.input = value;
    vm.runInContext(name + "(input)", context);
  }
  return { context, elements, call };
}

const t = (id, x, y) => ({ target_id: id, x, y, z: 0, speed: 0 });
function radar(targets, detected = true, presence = true) {
  return {
    frame_id: 9, detected, presence, zone: "ROOM",
    occupancy_state: presence ? "LIVE" : "ABSENT", targets,
  };
}

test("2D keeps same target ID when frame target order reverses", () => {
  const { elements, call } = fixture();
  call("showLiveData", radar([t(11, 0, 2), t(22, 1, 2)]));
  assert.equal(elements.target.textContent, 11);
  call("showLiveData", radar([t(22, 1.1, 2), t(11, 0.1, 2)]));
  assert.equal(elements.target.textContent, 11);
});

test("missing/null and OUTSIDE positions cannot become ROOM marker", () => {
  const { context, elements, call } = fixture();
  assert.equal(
    vm.runInContext("isInsidePhysicalRoom({x:null,y:2})", context), false,
  );
  assert.equal(
    vm.runInContext("isInsidePhysicalRoom({x:4,y:2})", context), false,
  );
  call("showLiveData", radar([t(11, 0, 2)]));
  call("showLiveData", {
    ...radar([t(20, 4, 2)], true, true),
    last_known_position: t(11, 0, 2),
  });
  assert.equal(elements.presence.textContent, "YES");
  assert.equal(elements.target.textContent, "~");
});

test("2D marker is smoothed but sensor numeric readout remains measured", () => {
  const { elements, call } = fixture();
  call("showLiveData", radar([t(11, 0, 2)]));
  const before = parseFloat(elements.target.style.left);
  call("showLiveData", radar([t(11, 1.7, 2)]));
  const after = parseFloat(elements.target.style.left);
  assert(after > before);
  assert(after < 97);
  assert.equal(elements.xValue.textContent, "1.70 m");
});

test("fast stream is not overwritten by a late one-second batch", () => {
  const { elements, call } = fixture();
  call("showFastLiveData", {
    frame_id: 11, targets: [t(11, 1.0, 2)], points: [],
  });
  const before = elements.target.style.left;
  call("showLiveData", radar([t(11, -1.5, 2)]));
  assert.equal(elements.target.style.left, before);
});

test("real absence removes 2D measurement, without changing DB", () => {
  const { elements, call } = fixture();
  call("showLiveData", radar([t(11, 0, 2)]));
  call("showLiveData", radar([], false, false));
  assert.equal(elements.presence.textContent, "NO");
  assert.equal(elements.targetId.textContent, "-");
});


test("speed readout changes with measured low and moving samples", () => {
  const { elements, call } = fixture();
  call("showLiveData", radar([{...t(11, 0, 2), speed: 0.02}]));
  assert.equal(elements.movementState.textContent, "저속 관측");
  call("showLiveData", radar([{...t(11, 0.2, 2), speed: 0.18}]));
  assert.equal(elements.movementState.textContent, "움직임 관측");
  // Preserve the original back-end occupancy state unchanged.
  assert.equal(elements.occupancyState.textContent, "LIVE");
});

test("a missing target never fabricates measured stillness", () => {
  const { elements, call } = fixture();
  call("showLiveData", radar([{...t(11, 0, 2), speed: 0.15}]));
  call("showLiveData", {
    ...radar([], false, true),
    occupancy_state: "HELD_STATIC",
    last_known_position: t(11, 0, 2),
  });
  assert.equal(elements.movementState.textContent, "미검출 · 재실 추정");
});

test("fast visualization sample updates the live movement readout", () => {
  const { elements, call } = fixture();
  call("showFastLiveData", {
    frame_id: 13, targets: [{...t(11, 0.2, 2), speed: 0.14}],
    points: [],
  });
  assert.equal(elements.movementState.textContent, "움직임 관측");
});
