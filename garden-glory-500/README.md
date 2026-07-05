# Garden Glory 500

Garden Glory 500 is a short single-player forest racing game for **MakeCode Arcade** and **Meowbit**. Players choose a mushroom or fruit avatar, build a car from pre-built parts, then race against three AI drivers through a decorated woodland circuit.

## Local validation

From this folder:

```powershell
pxt build
```

That validates the standalone Arcade package and builds the simulator JavaScript bundle.

## Emulator workflow

The most reliable emulator path for this project is the public Arcade editor:

1. Open `https://arcade.makecode.com/#editor`
2. Create a new JavaScript project named **Garden Glory 500**
3. Replace the starter code with `main.ts` from this folder
4. Use the built-in simulator in the editor to test and iterate

If you are working from a full `pxt-arcade` target checkout instead of this standalone project folder, you can also use:

```powershell
pxt serve
```

## Build for Meowbit

To deploy on Meowbit from the Arcade editor:

1. Connect the Meowbit by USB.
2. Put it into bootloader mode so it mounts as the `ARCADE` drive.
3. In the Arcade editor, choose **Download** to generate the `.uf2`.
4. Copy the downloaded `.uf2` onto the `ARCADE` drive.

## Controls

- **Title / menus:** Left and right choose, **A** confirms, **B** goes back
- **Race:** Up, down, left, and right drive the car
