# antsim

Ant colony simulators.

- `antsim-threejs.html` — 3D three.js version (single file, open in a browser). Live at https://antsim.clydeford.net
- `ant_colony_simulator-probabalistic.py` — pygame version with pheromone-based foraging
- `antsim.py` — original pygame sim

## Deploy

Cloudflare Worker serving static assets. With `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` set:

```
npm install
npm run deploy
```
