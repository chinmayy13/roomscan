# Capture protocol (Route 2: stock app) — one page

**Tier:** LiDAR. **Device:** an iPhone or iPad with LiDAR (iPhone 12 Pro / Pro Max or newer Pro, iPad Pro 2020 or newer).
**App:** *Stray Scanner* by Stray Robots, free on the App Store. Nothing else to install on the phone.

## Before you start (1 minute)
1. Install Stray Scanner from the App Store and open it once; allow camera access.
2. Switch on **every light** in the property. Open **all interior doors** fully.
3. Note where the main entrance is. You will start and finish standing there.

## Walking the property (2 to 5 minutes total)
1. Stand at the entrance, facing into the property. Tap the record button.
2. Hold the phone at **chest height**, screen facing you, camera pointing **slightly down**
   (you should see the floor-wall line at the bottom of the screen).
3. Walk **slowly**: about one step per second. Turn slowly: a full turn should take ~5 seconds.
4. In **every room**, including the corridor, bathrooms and balconies:
   - walk along the walls about 1 to 2 m away from them, so every wall and every corner is seen;
   - then stand in the middle and do **one slow full turn with the phone tilted up** so the
     **ceiling** fills the top half of the screen. *Do not skip this: without it the ceiling
     height is reported as "not captured".*
5. Pass through each doorway slowly, pointing the camera through the door before you step through.
6. When every room is done, **walk back to the entrance** and stand where you started for
   3 seconds. Then stop the recording.

## Avoid
- Running or swinging the phone. Blur and fast turns cause tracking drift.
- Standing close to **mirrors and large glass** and pointing straight at them; LiDAR sees
  "rooms" inside mirrors. Pass them at an angle.
- Covering the LiDAR sensor (the black dot by the cameras) with a finger.
- Dark rooms: if a room has no light, skip it and say so.

## Handing the files over
1. Open the **Files** app → *On My iPhone* → *Stray Scanner*. The newest folder (a random
   name like `c7d28f72c6`) is your capture.
2. Long-press it → **Compress**. Share the resulting `.zip` (AirDrop, Google Drive, USB).
3. On the laptop: `python -m roomscan path/to/that.zip --out out/property_name`

*(The engineer should verify step 1 of the handover on the actual test phone before the defense.)*
