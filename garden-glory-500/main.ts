namespace SpriteKind {
    export const Racer = SpriteKind.create()
}

enum FlowState {
    Title,
    Avatar,
    Body,
    Wheels,
    Accent,
    Racing,
    Results
}

class RacerState {
    sprite: Sprite
    isPlayer: boolean
    nextWaypoint: number
    lapsComplete: number
    vx: number
    vy: number
    maxSpeed: number
    accel: number
    offroadFactor: number
    finished: boolean
    finishRank: number
    aiSkill: number
    avatarIndex: number
    bodyIndex: number
    wheelIndex: number
    accentIndex: number

    constructor(sprite: Sprite, isPlayer: boolean, avatarIndex: number, bodyIndex: number, wheelIndex: number, accentIndex: number) {
        this.sprite = sprite
        this.isPlayer = isPlayer
        this.nextWaypoint = 0
        this.lapsComplete = 0
        this.vx = 0
        this.vy = 0
        this.maxSpeed = 1.7
        this.accel = 0.12
        this.offroadFactor = 0.55
        this.finished = false
        this.finishRank = 0
        this.aiSkill = 1
        this.avatarIndex = avatarIndex
        this.bodyIndex = bodyIndex
        this.wheelIndex = wheelIndex
        this.accentIndex = accentIndex
    }
}

const WORLD_W = 320
const WORLD_H = 240
const TOTAL_LAPS = 3
const RACE_LIMIT_MS = 80000
const WAYPOINT_RADIUS = 18
const waypointXs = [62, 112, 186, 256, 286, 286, 248, 182, 112, 58, 36, 38]
const waypointYs = [188, 214, 214, 194, 148, 84, 34, 26, 42, 82, 130, 170]

const avatarNames = [
    "Milo Morel",
    "Poppy Portobello",
    "Berry Blink",
    "Clementine Crew",
    "Apple Amp",
    "Pear Spark"
]
const avatarKinds = [0, 0, 1, 1, 1, 1]
const avatarMainColors = [9, 10, 2, 5, 8, 7]
const avatarAccentColors = [1, 15, 12, 15, 2, 6]

const bodyNames = ["Twig Buggy", "Leaf Roadster", "Pebble Pickup"]
const bodyColors = [6, 7, 14]
const bodySpeed = [1.85, 2.05, 1.7]
const bodyAccel = [0.13, 0.11, 0.15]

const wheelNames = ["Moss Tires", "Bark Treads", "Bloom Rims"]
const wheelColors = [15, 1, 5]
const wheelSpeedBonus = [0.0, -0.08, 0.05]
const wheelAccelBonus = [0.0, 0.03, -0.01]
const wheelOffroadFactor = [0.58, 0.72, 0.48]

const accentNames = ["Firefly Gold", "Berry Blue", "Petal Pink"]
const accentColors = [4, 11, 13]

let flowState = FlowState.Title
let selectedAvatar = 0
let selectedBody = 0
let selectedWheel = 0
let selectedAccent = 0
let previewSprite: Sprite = null
let menuBackground: Image = null
let trackBackground: Image = null
let roadMask: Image = null
let racers: RacerState[] = []
let playerRacer: RacerState = null
let finishers = 0
let raceStartedAt = 0
let endMessage = ""
let finalRank = 0
let lastStatusAt = 0
let lastPlayerX = 0
let lastPlayerY = 0

function moduloChoice(value: number, length: number): number {
    let result = value % length
    if (result < 0) {
        result += length
    }
    return result
}

function paintCircle(img: Image, cx: number, cy: number, radius: number, color: number) {
    for (let dx = -radius; dx <= radius; dx++) {
        for (let dy = -radius; dy <= radius; dy++) {
            if (dx * dx + dy * dy <= radius * radius) {
                let px = cx + dx
                let py = cy + dy
                if (px >= 0 && px < img.width && py >= 0 && py < img.height) {
                    img.setPixel(px, py, color)
                }
            }
        }
    }
}

function paintSegment(img: Image, x1: number, y1: number, x2: number, y2: number, radius: number, color: number) {
    let dx = x2 - x1
    let dy = y2 - y1
    let steps = Math.max(Math.abs(dx), Math.abs(dy))
    if (steps < 1) {
        paintCircle(img, x1, y1, radius, color)
        return
    }
    for (let step = 0; step <= steps; step++) {
        let x = Math.round(x1 + dx * step / steps)
        let y = Math.round(y1 + dy * step / steps)
        paintCircle(img, x, y, radius, color)
    }
}

function drawLeaf(img: Image, x: number, y: number, color: number) {
    img.setPixel(x, y, color)
    img.setPixel(x + 1, y, color)
    img.setPixel(x, y + 1, color)
    img.setPixel(x + 1, y + 1, color)
    img.setPixel(x + 2, y + 1, color)
}

function drawPebble(img: Image, x: number, y: number) {
    img.setPixel(x, y, 14)
    img.setPixel(x + 1, y, 15)
    img.setPixel(x, y + 1, 15)
}

function drawTwig(img: Image, x: number, y: number) {
    for (let i = 0; i < 4; i++) {
        let px = x + i
        let py = y + ((i + 1) / 2 >> 0)
        if (px >= 0 && py >= 0 && px < img.width && py < img.height) {
            img.setPixel(px, py, 6)
        }
    }
}

function drawShrub(img: Image, x: number, y: number) {
    paintCircle(img, x, y, 4, 7)
    paintCircle(img, x - 3, y + 1, 3, 12)
    paintCircle(img, x + 3, y + 1, 3, 12)
}

function drawFlower(img: Image, x: number, y: number) {
    img.setPixel(x, y + 3, 7)
    img.setPixel(x, y + 2, 7)
    img.setPixel(x, y + 1, 7)
    img.setPixel(x, y, 15)
    img.setPixel(x - 1, y + 1, 13)
    img.setPixel(x + 1, y + 1, 13)
    img.setPixel(x, y + 2, 13)
}

function createMenuBackground(): Image {
    let bg = image.create(screen.width, screen.height)
    bg.fill(7)
    for (let x = 0; x < screen.width; x += 10) {
        paintCircle(bg, x, 0, 4, 12)
        paintCircle(bg, x, screen.height - 1, 4, 12)
    }
    for (let y = 0; y < screen.height; y += 10) {
        paintCircle(bg, 0, y, 4, 12)
        paintCircle(bg, screen.width - 1, y, 4, 12)
    }
    for (let i = 0; i < 24; i++) {
        drawFlower(bg, randint(8, screen.width - 8), randint(16, screen.height - 12))
    }
    for (let j = 0; j < 18; j++) {
        drawLeaf(bg, randint(6, screen.width - 6), randint(12, screen.height - 8), randint(8, 10))
    }
    return bg
}

function buildAvatarPreview(index: number): Image {
    let img = image.create(28, 28)
    let mainColor = avatarMainColors[index]
    let accentColor = avatarAccentColors[index]
    if (avatarKinds[index] == 0) {
        paintCircle(img, 14, 8, 7, mainColor)
        paintCircle(img, 11, 7, 2, accentColor)
        paintCircle(img, 17, 6, 2, accentColor)
        paintCircle(img, 15, 10, 2, accentColor)
        img.fillRect(10, 11, 8, 8, 2)
        img.fillRect(7, 14, 3, 2, 2)
        img.fillRect(18, 14, 3, 2, 2)
        img.fillRect(11, 19, 2, 5, 6)
        img.fillRect(15, 19, 2, 5, 6)
        img.setPixel(12, 14, 15)
        img.setPixel(15, 14, 15)
        img.setPixel(12, 15, 1)
        img.setPixel(15, 15, 1)
        img.setPixel(13, 17, 1)
        img.setPixel(14, 17, 1)
    } else {
        paintCircle(img, 14, 11, 7, mainColor)
        paintCircle(img, 17, 7, 2, accentColor)
        img.setPixel(14, 3, 6)
        img.setPixel(15, 2, 6)
        img.setPixel(16, 1, 7)
        img.setPixel(17, 2, 7)
        img.fillRect(7, 14, 3, 2, 2)
        img.fillRect(18, 14, 3, 2, 2)
        img.fillRect(11, 19, 2, 5, 6)
        img.fillRect(15, 19, 2, 5, 6)
        img.setPixel(12, 12, 15)
        img.setPixel(15, 12, 15)
        img.setPixel(12, 13, 1)
        img.setPixel(15, 13, 1)
        img.setPixel(13, 16, 1)
        img.setPixel(14, 16, 1)
    }
    return img
}

function buildCarImage(bodyIndex: number, wheelIndex: number, accentIndex: number, avatarIndex: number, direction: number): Image {
    let img = image.create(24, 24)
    let bodyColor = bodyColors[bodyIndex]
    let wheelColor = wheelColors[wheelIndex]
    let accentColor = accentColors[accentIndex]
    let headColor = avatarMainColors[avatarIndex]
    let trimColor = avatarAccentColors[avatarIndex]
    if (direction == 0) {
        img.fillRect(7, 4, 10, 15, bodyColor)
        img.fillRect(9, 2, 6, 4, accentColor)
        img.fillRect(8, 8, 8, 6, 2)
        img.fillRect(6, 6, 2, 4, wheelColor)
        img.fillRect(16, 6, 2, 4, wheelColor)
        img.fillRect(6, 13, 2, 4, wheelColor)
        img.fillRect(16, 13, 2, 4, wheelColor)
        img.fillRect(10, 9, 4, 3, headColor)
        img.setPixel(11, 10, 15)
        img.setPixel(12, 10, 15)
        img.setPixel(11, 11, trimColor)
        img.setPixel(12, 11, trimColor)
    } else if (direction == 1) {
        img.fillRect(4, 7, 15, 10, bodyColor)
        img.fillRect(18, 9, 4, 6, accentColor)
        img.fillRect(9, 8, 6, 8, 2)
        img.fillRect(6, 6, 4, 2, wheelColor)
        img.fillRect(6, 16, 4, 2, wheelColor)
        img.fillRect(13, 6, 4, 2, wheelColor)
        img.fillRect(13, 16, 4, 2, wheelColor)
        img.fillRect(10, 10, 3, 4, headColor)
        img.setPixel(11, 11, 15)
        img.setPixel(11, 12, trimColor)
    } else if (direction == 2) {
        img.fillRect(7, 5, 10, 15, bodyColor)
        img.fillRect(9, 18, 6, 4, accentColor)
        img.fillRect(8, 10, 8, 6, 2)
        img.fillRect(6, 7, 2, 4, wheelColor)
        img.fillRect(16, 7, 2, 4, wheelColor)
        img.fillRect(6, 14, 2, 4, wheelColor)
        img.fillRect(16, 14, 2, 4, wheelColor)
        img.fillRect(10, 11, 4, 3, headColor)
        img.setPixel(11, 12, 15)
        img.setPixel(12, 12, 15)
        img.setPixel(11, 13, trimColor)
        img.setPixel(12, 13, trimColor)
    } else {
        img.fillRect(5, 7, 15, 10, bodyColor)
        img.fillRect(2, 9, 4, 6, accentColor)
        img.fillRect(9, 8, 6, 8, 2)
        img.fillRect(7, 6, 4, 2, wheelColor)
        img.fillRect(7, 16, 4, 2, wheelColor)
        img.fillRect(14, 6, 4, 2, wheelColor)
        img.fillRect(14, 16, 4, 2, wheelColor)
        img.fillRect(11, 10, 3, 4, headColor)
        img.setPixel(12, 11, 15)
        img.setPixel(12, 12, trimColor)
    }
    return img
}

function choiceTitle(): string {
    if (flowState == FlowState.Avatar) {
        return "Choose your avatar"
    } else if (flowState == FlowState.Body) {
        return "Choose your body"
    } else if (flowState == FlowState.Wheels) {
        return "Choose your wheels"
    } else {
        return "Choose your accent"
    }
}

function choiceValue(): string {
    if (flowState == FlowState.Avatar) {
        return avatarNames[selectedAvatar]
    } else if (flowState == FlowState.Body) {
        return bodyNames[selectedBody]
    } else if (flowState == FlowState.Wheels) {
        return wheelNames[selectedWheel]
    } else {
        return accentNames[selectedAccent]
    }
}

function renderMenuScreen() {
    if (!menuBackground) {
        menuBackground = createMenuBackground()
    }
    let bg = menuBackground.clone()
    bg.fillRect(0, 0, 160, 20, 1)
    bg.print("Garden Glory 500", 26, 6, 15)
    if (flowState == FlowState.Title) {
        bg.fillRect(8, 92, 144, 30, 1)
        bg.print("Forest sprint for 1 player", 16, 96, 15)
        bg.print("A start  B none", 34, 108, 10)
    } else {
        bg.fillRect(8, 92, 144, 30, 1)
        bg.print(choiceTitle(), 20, 94, 15)
        bg.print("< " + choiceValue() + " >", 18, 106, 10)
        bg.print("A ok  B back", 46, 118, 15)
    }
    scene.setBackgroundImage(bg)
}

function refreshPreview() {
    if (flowState == FlowState.Racing || flowState == FlowState.Results) {
        return
    }
    renderMenuScreen()
    if (previewSprite) {
        previewSprite.destroy()
    }
    if (flowState == FlowState.Avatar) {
        previewSprite = sprites.create(buildAvatarPreview(selectedAvatar), SpriteKind.Player)
    } else {
        previewSprite = sprites.create(buildCarImage(selectedBody, selectedWheel, selectedAccent, selectedAvatar, 1), SpriteKind.Player)
    }
    previewSprite.setFlag(SpriteFlag.Ghost, true)
    previewSprite.x = 80
    previewSprite.y = 70
}

function moveChoice(delta: number) {
    if (flowState == FlowState.Avatar) {
        selectedAvatar = moduloChoice(selectedAvatar + delta, avatarNames.length)
    } else if (flowState == FlowState.Body) {
        selectedBody = moduloChoice(selectedBody + delta, bodyNames.length)
    } else if (flowState == FlowState.Wheels) {
        selectedWheel = moduloChoice(selectedWheel + delta, wheelNames.length)
    } else if (flowState == FlowState.Accent) {
        selectedAccent = moduloChoice(selectedAccent + delta, accentNames.length)
    }
    refreshPreview()
}

function beginMenus() {
    flowState = FlowState.Title
    if (!menuBackground) {
        menuBackground = createMenuBackground()
    }
    renderMenuScreen()
    previewSprite = sprites.create(buildCarImage(selectedBody, selectedWheel, selectedAccent, selectedAvatar, 1), SpriteKind.Player)
    previewSprite.setFlag(SpriteFlag.Ghost, true)
    previewSprite.x = 80
    previewSprite.y = 72
}

function buildTrack() {
    trackBackground = image.create(WORLD_W, WORLD_H)
    roadMask = image.create(WORLD_W, WORLD_H)
    trackBackground.fill(7)
    for (let i = 0; i < waypointXs.length; i++) {
        let next = (i + 1) % waypointXs.length
        paintSegment(trackBackground, waypointXs[i], waypointYs[i], waypointXs[next], waypointYs[next], 18, 5)
        paintSegment(trackBackground, waypointXs[i], waypointYs[i], waypointXs[next], waypointYs[next], 14, 13)
        paintSegment(roadMask, waypointXs[i], waypointYs[i], waypointXs[next], waypointYs[next], 14, 1)
    }
    for (let i = 0; i < 260; i++) {
        let x = randint(2, WORLD_W - 3)
        let y = randint(2, WORLD_H - 3)
        if (roadMask.getPixel(x, y) == 0) {
            let detail = randint(0, 2)
            if (detail == 0) {
                drawLeaf(trackBackground, x, y, randint(8, 10))
            } else if (detail == 1) {
                drawPebble(trackBackground, x, y)
            } else {
                drawTwig(trackBackground, x, y)
            }
        }
    }
    for (let i = 0; i < 55; i++) {
        let x = randint(8, WORLD_W - 8)
        let y = randint(8, WORLD_H - 8)
        if (roadMask.getPixel(x, y) == 0) {
            if (randint(0, 1) == 0) {
                drawShrub(trackBackground, x, y)
            } else {
                drawFlower(trackBackground, x, y)
            }
        }
    }
    for (let x = 40; x < 70; x += 4) {
        for (let y = 174; y < 186; y += 4) {
            let checkerColor = ((x + y) / 4) % 2 == 0 ? 1 : 15
            trackBackground.fillRect(x, y, 4, 4, checkerColor)
        }
    }
    scene.setBackgroundImage(trackBackground)
}

function directionFromVelocity(vx: number, vy: number): number {
    if (Math.abs(vx) >= Math.abs(vy)) {
        return vx >= 0 ? 1 : 3
    } else {
        return vy >= 0 ? 2 : 0
    }
}

function applyStats(racer: RacerState) {
    racer.maxSpeed = bodySpeed[racer.bodyIndex] + wheelSpeedBonus[racer.wheelIndex]
    racer.accel = bodyAccel[racer.bodyIndex] + wheelAccelBonus[racer.wheelIndex]
    racer.offroadFactor = wheelOffroadFactor[racer.wheelIndex]
}

function playerDriveSpeed(racer: RacerState): number {
    return Math.round(40 + racer.maxSpeed * 24)
}

function aiDriveSpeed(racer: RacerState): number {
    return racer.maxSpeed * 0.62 * racer.aiSkill
}

function createRacer(x: number, y: number, avatarIndex: number, bodyIndex: number, wheelIndex: number, accentIndex: number, isPlayer: boolean): RacerState {
    let sprite = sprites.create(buildCarImage(bodyIndex, wheelIndex, accentIndex, avatarIndex, 1), SpriteKind.Racer)
    sprite.setFlag(SpriteFlag.Ghost, true)
    sprite.z = 10
    sprite.x = x
    sprite.y = y
    let racer = new RacerState(sprite, isPlayer, avatarIndex, bodyIndex, wheelIndex, accentIndex)
    applyStats(racer)
    return racer
}

function buildOpponents() {
    let startXs = [34, 46, 58, 70]
    let startYs = [188, 182, 188, 182]
    racers = []
    finishers = 0
    playerRacer = createRacer(startXs[0], startYs[0], selectedAvatar, selectedBody, selectedWheel, selectedAccent, true)
    racers.push(playerRacer)
    for (let i = 1; i < 4; i++) {
        let avatarIndex = moduloChoice(selectedAvatar + i, avatarNames.length)
        let bodyIndex = randint(0, bodyNames.length - 1)
        let wheelIndex = randint(0, wheelNames.length - 1)
        let accentIndex = randint(0, accentNames.length - 1)
        let rival = createRacer(startXs[i], startYs[i], avatarIndex, bodyIndex, wheelIndex, accentIndex, false)
        rival.aiSkill = 0.96 + i * 0.03
        racers.push(rival)
    }
    scene.cameraFollowSprite(playerRacer.sprite)
}

function startRace() {
    if (previewSprite) {
        previewSprite.destroy()
        previewSprite = null
    }
    buildTrack()
    buildOpponents()
    raceStartedAt = game.runtime()
    lastStatusAt = raceStartedAt
    flowState = FlowState.Racing
    lastPlayerX = playerRacer.sprite.x
    lastPlayerY = playerRacer.sprite.y
    playerRacer.sprite.sayText("Go!", 800, false)
}

function clampToWorld(racer: RacerState) {
    if (racer.sprite.x < 8) {
        racer.sprite.x = 8
        racer.vx = 0
    } else if (racer.sprite.x > WORLD_W - 8) {
        racer.sprite.x = WORLD_W - 8
        racer.vx = 0
    }
    if (racer.sprite.y < 8) {
        racer.sprite.y = 8
        racer.vy = 0
    } else if (racer.sprite.y > WORLD_H - 8) {
        racer.sprite.y = WORLD_H - 8
        racer.vy = 0
    }
}

function onRoad(racer: RacerState): boolean {
    return roadMask && roadMask.getPixel(racer.sprite.x >> 0, racer.sprite.y >> 0) != 0
}

function clampVelocity(racer: RacerState, maxSpeed: number) {
    let magnitude = Math.sqrt(racer.vx * racer.vx + racer.vy * racer.vy)
    if (magnitude > maxSpeed && magnitude > 0) {
        racer.vx = racer.vx / magnitude * maxSpeed
        racer.vy = racer.vy / magnitude * maxSpeed
    }
}

function updatePlayerDrive() {
    if (playerRacer.finished) {
        playerRacer.vx = 0
        playerRacer.vy = 0
    } else {
        let driveSpeed = playerDriveSpeed(playerRacer)
        if (!onRoad(playerRacer)) {
            driveSpeed = Math.round(driveSpeed * playerRacer.offroadFactor)
        }
        playerRacer.vx = controller.dx(driveSpeed)
        playerRacer.vy = controller.dy(driveSpeed)
        playerRacer.sprite.x += playerRacer.vx
        playerRacer.sprite.y += playerRacer.vy
    }
    playerRacer.vx = playerRacer.sprite.x - lastPlayerX
    playerRacer.vy = playerRacer.sprite.y - lastPlayerY
    lastPlayerX = playerRacer.sprite.x
    lastPlayerY = playerRacer.sprite.y
    clampToWorld(playerRacer)
    playerRacer.sprite.setImage(buildCarImage(playerRacer.bodyIndex, playerRacer.wheelIndex, playerRacer.accentIndex, playerRacer.avatarIndex, directionFromVelocity(playerRacer.vx, playerRacer.vy)))
}

function updateAiDrive(racer: RacerState) {
    if (racer.finished) {
        racer.vx = 0
        racer.vy = 0
    } else {
        let targetX = waypointXs[racer.nextWaypoint]
        let targetY = waypointYs[racer.nextWaypoint]
        let dx = targetX - racer.sprite.x
        let dy = targetY - racer.sprite.y
        let distance = Math.sqrt(dx * dx + dy * dy)
        if (distance > 0) {
            let step = aiDriveSpeed(racer)
            if (!onRoad(racer)) {
                step *= racer.offroadFactor
            }
            racer.vx = dx / distance * step
            racer.vy = dy / distance * step
            if (distance <= step) {
                racer.sprite.x = targetX
                racer.sprite.y = targetY
            } else {
                racer.sprite.x += racer.vx
                racer.sprite.y += racer.vy
            }
        } else {
            racer.vx = 0
            racer.vy = 0
        }
    }
    clampToWorld(racer)
    racer.sprite.setImage(buildCarImage(racer.bodyIndex, racer.wheelIndex, racer.accentIndex, racer.avatarIndex, directionFromVelocity(racer.vx, racer.vy)))
}

function finishRacer(racer: RacerState) {
    if (racer.finished) {
        return
    }
    finishers += 1
    racer.finished = true
    racer.finishRank = finishers
}

function updateWaypointProgress(racer: RacerState) {
    if (racer.finished) {
        return
    }
    let dx = waypointXs[racer.nextWaypoint] - racer.sprite.x
    let dy = waypointYs[racer.nextWaypoint] - racer.sprite.y
    if (dx * dx + dy * dy <= WAYPOINT_RADIUS * WAYPOINT_RADIUS) {
        racer.nextWaypoint += 1
        if (racer.nextWaypoint >= waypointXs.length) {
            racer.nextWaypoint = 0
            racer.lapsComplete += 1
            if (racer.isPlayer && racer.lapsComplete < TOTAL_LAPS) {
                racer.sprite.sayText("Lap " + (racer.lapsComplete + 1) + " of " + TOTAL_LAPS, 900, false)
            }
            if (racer.lapsComplete >= TOTAL_LAPS) {
                finishRacer(racer)
            }
        }
    }
}

function progressScore(racer: RacerState): number {
    if (racer.finished) {
        return 10000 - racer.finishRank
    }
    let dx = waypointXs[racer.nextWaypoint] - racer.sprite.x
    let dy = waypointYs[racer.nextWaypoint] - racer.sprite.y
    let distance = Math.sqrt(dx * dx + dy * dy)
    return racer.lapsComplete * waypointXs.length + racer.nextWaypoint - Math.min(distance, 200) / 200
}

function rankFor(racer: RacerState): number {
    let rank = 1
    let mine = progressScore(racer)
    for (let i = 0; i < racers.length; i++) {
        if (racers[i] != racer && progressScore(racers[i]) > mine) {
            rank += 1
        }
    }
    return rank
}

function ordinal(value: number): string {
    if (value == 1) {
        return "1st"
    } else if (value == 2) {
        return "2nd"
    } else if (value == 3) {
        return "3rd"
    } else {
        return "" + value + "th"
    }
}

function endRace(message: string) {
    if (flowState == FlowState.Results) {
        return
    }
    flowState = FlowState.Results
    endMessage = message
    finalRank = rankFor(playerRacer)
    game.splash("Garden Glory 500", endMessage)
    game.splash("You placed " + ordinal(finalRank), "Avatar: " + avatarNames[selectedAvatar])
    game.over(finalRank <= 2, finalRank == 1 ? effects.confetti : effects.smiles)
}

controller.left.onEvent(ControllerButtonEvent.Pressed, function () {
    if (flowState == FlowState.Avatar || flowState == FlowState.Body || flowState == FlowState.Wheels || flowState == FlowState.Accent) {
        moveChoice(-1)
    }
})

controller.right.onEvent(ControllerButtonEvent.Pressed, function () {
    if (flowState == FlowState.Avatar || flowState == FlowState.Body || flowState == FlowState.Wheels || flowState == FlowState.Accent) {
        moveChoice(1)
    }
})

controller.A.onEvent(ControllerButtonEvent.Pressed, function () {
    if (flowState == FlowState.Title) {
        flowState = FlowState.Avatar
        refreshPreview()
    } else if (flowState == FlowState.Avatar) {
        flowState = FlowState.Body
        refreshPreview()
    } else if (flowState == FlowState.Body) {
        flowState = FlowState.Wheels
        refreshPreview()
    } else if (flowState == FlowState.Wheels) {
        flowState = FlowState.Accent
        refreshPreview()
    } else if (flowState == FlowState.Accent) {
        startRace()
    }
})

controller.B.onEvent(ControllerButtonEvent.Pressed, function () {
    if (flowState == FlowState.Body) {
        flowState = FlowState.Avatar
        refreshPreview()
    } else if (flowState == FlowState.Wheels) {
        flowState = FlowState.Body
        refreshPreview()
    } else if (flowState == FlowState.Accent) {
        flowState = FlowState.Wheels
        refreshPreview()
    }
})

game.onUpdate(function () {
    if (flowState != FlowState.Racing) {
        return
    }
    updatePlayerDrive()
    for (let i = 1; i < racers.length; i++) {
        updateAiDrive(racers[i])
    }
    for (let i = 0; i < racers.length; i++) {
        updateWaypointProgress(racers[i])
    }
    if (playerRacer.finished) {
        endRace("You crossed the finish line!")
        return
    }
    if (game.runtime() - raceStartedAt >= RACE_LIMIT_MS) {
        endRace("Time ran out in the garden!")
        return
    }
    if (game.runtime() - lastStatusAt >= 1500) {
        lastStatusAt = game.runtime()
        let remaining = Math.max(0, (RACE_LIMIT_MS - (game.runtime() - raceStartedAt)) / 1000 >> 0)
        playerRacer.sprite.sayText("Lap " + (Math.min(playerRacer.lapsComplete + 1, TOTAL_LAPS)) + "  Rank " + rankFor(playerRacer) + "  " + remaining + "s", 700, false)
    }
})

beginMenus()
