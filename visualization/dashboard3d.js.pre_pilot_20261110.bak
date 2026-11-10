import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";


const SENSOR_HEIGHT = 0.75;

const ROOM_X_MIN = -1.8;
const ROOM_X_MAX = 1.8;
const ROOM_Y_MIN = 0.0;
const ROOM_Y_MAX = 3.8;

const BED_X_MIN = -1.8;
const BED_X_MAX = 0.0;
const BED_Y_MIN = 1.6;
const BED_Y_MAX = 2.6;

const EXIT_X_MIN = 0.95;
const EXIT_X_MAX = 1.65;
const EXIT_Y_MIN = 2.90;
const EXIT_Y_MAX = 3.70;

const MAX_RENDER_POINTS = 96;


const host =
    document.getElementById("pointCloud3d");

const cloudPointCount =
    document.getElementById("cloudPointCount");

const cloudRate =
    document.getElementById("cloudRate");

const cloudFrameId =
    document.getElementById("cloudFrameId");

const cloudStatus =
    document.getElementById("cloudStatus");


if (!host) {
    throw new Error("pointCloud3d host not found");
}


const scene = new THREE.Scene();
scene.background = new THREE.Color(0x11161b);
scene.fog = new THREE.Fog(0x11161b, 6.0, 12.0);


const camera = new THREE.PerspectiveCamera(
    48,
    1,
    0.05,
    30
);

camera.position.set(
    4.6,
    3.5,
    4.8
);


const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: false,
});

renderer.setPixelRatio(
    Math.min(
        window.devicePixelRatio || 1,
        2
    )
);

renderer.outputColorSpace =
    THREE.SRGBColorSpace;

host.appendChild(
    renderer.domElement
);


const controls =
    new OrbitControls(
        camera,
        renderer.domElement
    );

controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(
    0,
    1.0,
    -1.9
);
controls.minDistance = 2.2;
controls.maxDistance = 12.0;
controls.maxPolarAngle =
    Math.PI * 0.49;
controls.update();


function radarToThree(
    x,
    y,
    z
) {
    return new THREE.Vector3(
        Number(x),
        SENSOR_HEIGHT + Number(z),
        -Number(y)
    );
}


function addRoomFloor() {
    const width =
        ROOM_X_MAX - ROOM_X_MIN;

    const depth =
        ROOM_Y_MAX - ROOM_Y_MIN;

    const floorGeometry =
        new THREE.PlaneGeometry(
            width,
            depth
        );

    const floorMaterial =
        new THREE.MeshBasicMaterial({
            color: 0x1b2229,
            transparent: true,
            opacity: 0.92,
            side: THREE.DoubleSide,
        });

    const floor =
        new THREE.Mesh(
            floorGeometry,
            floorMaterial
        );

    floor.rotation.x =
        -Math.PI / 2;

    floor.position.set(
        0,
        0,
        -depth / 2
    );

    scene.add(floor);


    const grid =
        new THREE.GridHelper(
            4.4,
            22,
            0x65717c,
            0x303942
        );

    grid.position.set(
        0,
        0.006,
        -2.0
    );

    scene.add(grid);


    const outlinePoints = [
        new THREE.Vector3(ROOM_X_MIN, 0.02, 0),
        new THREE.Vector3(ROOM_X_MAX, 0.02, 0),
        new THREE.Vector3(ROOM_X_MAX, 0.02, -ROOM_Y_MAX),
        new THREE.Vector3(ROOM_X_MIN, 0.02, -ROOM_Y_MAX),
        new THREE.Vector3(ROOM_X_MIN, 0.02, 0),
    ];

    const outlineGeometry =
        new THREE.BufferGeometry()
            .setFromPoints(outlinePoints);

    const outline =
        new THREE.Line(
            outlineGeometry,
            new THREE.LineBasicMaterial({
                color: 0xc7d0d9,
            })
        );

    scene.add(outline);
}


function addBed() {
    const width =
        BED_X_MAX - BED_X_MIN;

    const depth =
        BED_Y_MAX - BED_Y_MIN;

    const bedHeight = 0.62;

    const geometry =
        new THREE.BoxGeometry(
            width,
            bedHeight,
            depth
        );

    const material =
        new THREE.MeshBasicMaterial({
            color: 0x6c7781,
            transparent: true,
            opacity: 0.22,
            wireframe: false,
        });

    const bed =
        new THREE.Mesh(
            geometry,
            material
        );

    bed.position.set(
        (BED_X_MIN + BED_X_MAX) / 2,
        bedHeight / 2,
        -(
            (BED_Y_MIN + BED_Y_MAX) /
            2
        )
    );

    scene.add(bed);

    const edges =
        new THREE.LineSegments(
            new THREE.EdgesGeometry(geometry),
            new THREE.LineBasicMaterial({
                color: 0xaeb8c1,
            })
        );

    edges.position.copy(
        bed.position
    );

    scene.add(edges);
}


function addExitZone() {
    const width =
        EXIT_X_MAX - EXIT_X_MIN;

    const depth =
        EXIT_Y_MAX - EXIT_Y_MIN;

    const geometry =
        new THREE.PlaneGeometry(
            width,
            depth
        );

    const material =
        new THREE.MeshBasicMaterial({
            color: 0x67727d,
            transparent: true,
            opacity: 0.25,
            side: THREE.DoubleSide,
        });

    const exit =
        new THREE.Mesh(
            geometry,
            material
        );

    exit.rotation.x =
        -Math.PI / 2;

    exit.position.set(
        (EXIT_X_MIN + EXIT_X_MAX) / 2,
        0.015,
        -(
            (EXIT_Y_MIN + EXIT_Y_MAX) /
            2
        )
    );

    scene.add(exit);
}


function addRadar() {
    const geometry =
        new THREE.SphereGeometry(
            0.07,
            16,
            12
        );

    const material =
        new THREE.MeshBasicMaterial({
            color: 0xffffff,
        });

    const radar =
        new THREE.Mesh(
            geometry,
            material
        );

    radar.position.set(
        0,
        SENSOR_HEIGHT,
        0
    );

    scene.add(radar);


    const directionGeometry =
        new THREE.ConeGeometry(
            0.10,
            0.32,
            16
        );

    const direction =
        new THREE.Mesh(
            directionGeometry,
            new THREE.MeshBasicMaterial({
                color: 0x9ba7b1,
                transparent: true,
                opacity: 0.7,
            })
        );

    direction.rotation.x =
        -Math.PI / 2;

    direction.position.set(
        0,
        SENSOR_HEIGHT,
        -0.18
    );

    scene.add(direction);
}


addRoomFloor();
addBed();
addExitZone();
addRadar();


let pointObject = null;
let targetGroup =
    new THREE.Group();

scene.add(targetGroup);


function clearPointCloud() {
    if (!pointObject) {
        return;
    }

    scene.remove(pointObject);

    pointObject.geometry.dispose();
    pointObject.material.dispose();

    pointObject = null;
}


function updatePointCloud(points) {
    clearPointCloud();

    if (!Array.isArray(points)) {
        points = [];
    }

    const valid = [];

    for (const item of points) {
        if (
            !Array.isArray(item) ||
            item.length < 3
        ) {
            continue;
        }

        const x = Number(item[0]);
        const y = Number(item[1]);
        const z = Number(item[2]);

        if (
            !Number.isFinite(x) ||
            !Number.isFinite(y) ||
            !Number.isFinite(z)
        ) {
            continue;
        }

        // Sanity limits are wider than the physical test room so that
        // OUTSIDE clutter/ghosts remain visible for debugging.
        if (
            x < -4.2 || x > 4.2 ||
            y < -0.2 || y > 8.2 ||
            z < -3.0 || z > 3.0
        ) {
            continue;
        }

        valid.push(item);

        if (
            valid.length >=
            MAX_RENDER_POINTS
        ) {
            break;
        }
    }

    cloudPointCount.textContent =
        String(valid.length);

    if (valid.length === 0) {
        return;
    }

    const positions =
        new Float32Array(
            valid.length * 3
        );

    for (
        let i = 0;
        i < valid.length;
        i++
    ) {
        const item = valid[i];

        const point = radarToThree(
            item[0],
            item[1],
            item[2]
        );

        positions[(i * 3) + 0] =
            point.x;

        positions[(i * 3) + 1] =
            point.y;

        positions[(i * 3) + 2] =
            point.z;
    }

    const geometry =
        new THREE.BufferGeometry();

    geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(
            positions,
            3
        )
    );

    const material =
        new THREE.PointsMaterial({
            color: 0x64d2ff,
            size: 0.065,
            sizeAttenuation: true,
            transparent: true,
            opacity: 0.95,
        });

    pointObject =
        new THREE.Points(
            geometry,
            material
        );

    scene.add(pointObject);
}


function clearTargets() {
    while (
        targetGroup.children.length > 0
    ) {
        const child =
            targetGroup.children.pop();

        if (child.geometry) {
            child.geometry.dispose();
        }

        if (child.material) {
            child.material.dispose();
        }
    }
}


function isInsideRoom(target) {
    const x = Number(target.x);
    const y = Number(target.y);

    return (
        Number.isFinite(x) &&
        Number.isFinite(y) &&
        x >= ROOM_X_MIN &&
        x <= ROOM_X_MAX &&
        y >= ROOM_Y_MIN &&
        y <= ROOM_Y_MAX
    );
}


function updateTargets(targets) {
    clearTargets();

    if (!Array.isArray(targets)) {
        return;
    }

    for (const target of targets) {
        if (!isInsideRoom(target)) {
            continue;
        }

        const x = Number(target.x);
        const y = Number(target.y);
        const z = Number(target.z ?? 0);

        if (!Number.isFinite(z)) {
            continue;
        }

        const position =
            radarToThree(x, y, z);

        const marker =
            new THREE.Mesh(
                new THREE.SphereGeometry(
                    0.09,
                    18,
                    14
                ),
                new THREE.MeshBasicMaterial({
                    color: 0xff9f0a,
                })
            );

        marker.position.copy(position);

        targetGroup.add(marker);
    }
}


const rateSamples = [];
let lastCloudAt = 0;


function updateRate() {
    const now = performance.now();

    rateSamples.push(now);

    while (
        rateSamples.length > 0 &&
        now - rateSamples[0] > 1500
    ) {
        rateSamples.shift();
    }

    if (rateSamples.length < 2) {
        cloudRate.textContent = "- Hz";
        return;
    }

    const durationSeconds =
        (
            rateSamples[rateSamples.length - 1] -
            rateSamples[0]
        ) / 1000;

    const hz =
        (rateSamples.length - 1) /
        Math.max(durationSeconds, 0.001);

    cloudRate.textContent =
        `${hz.toFixed(1)} Hz`;
}


window.addEventListener(
    "carewave:fast-live",
    (event) => {
        const data = event.detail || {};

        lastCloudAt = Date.now();

        cloudStatus.textContent =
            "LIVE";

        cloudFrameId.textContent =
            data.frame_id ?? "-";

        updatePointCloud(
            data.points
        );

        updateTargets(
            data.targets
        );

        updateRate();
    }
);


setInterval(
    () => {
        if (
            lastCloudAt > 0 &&
            Date.now() - lastCloudAt > 1800
        ) {
            cloudStatus.textContent =
                "WAITING";

            cloudRate.textContent =
                "- Hz";

            clearPointCloud();
            clearTargets();
            cloudPointCount.textContent = "0";
        }
    },
    500
);


function resizeRenderer() {
    const width =
        Math.max(
            host.clientWidth,
            1
        );

    const height =
        Math.max(
            host.clientHeight,
            1
        );

    renderer.setSize(
        width,
        height,
        false
    );

    camera.aspect =
        width / height;

    camera.updateProjectionMatrix();
}


const resizeObserver =
    new ResizeObserver(
        resizeRenderer
    );

resizeObserver.observe(host);
resizeRenderer();


function animate() {
    requestAnimationFrame(animate);

    controls.update();
    renderer.render(
        scene,
        camera
    );
}


cloudStatus.textContent = "READY";
animate();
