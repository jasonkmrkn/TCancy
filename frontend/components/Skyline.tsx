// Decorative skyline. Fully deterministic (integer hash, no Math.random) so server and client render identically.

const BUILDINGS = [
    { x: -20, w: 96, h: 120 },
    { x: 84, w: 86, h: 190 },
    { x: 178, w: 100, h: 100 },
    { x: 286, w: 90, h: 262 },
    { x: 384, w: 118, h: 150 },
    { x: 510, w: 84, h: 205 },
    { x: 602, w: 108, h: 128 },
    { x: 718, w: 102, h: 178 },
];

const VIEW_H = 300;
const COL = 17;
const ROW = 19;

function hash(n: number) {
    let x = Math.imul(n ^ (n >>> 15), 2246822519);
    x = Math.imul(x ^ (x >>> 13), 3266489917);
    return ((x ^ (x >>> 16)) >>> 0) % 1000;
}

export default function Skyline() {
    return (
        <svg
            aria-hidden
            viewBox={`0 0 800 ${VIEW_H}`}
            preserveAspectRatio="xMidYMax slice"
            className="pointer-events-none relative -mx-10 -mb-10 mt-auto h-44 w-[calc(100%+5rem)] max-w-none shrink-0"
        >
            <defs>
                <linearGradient id="skyline-body" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#27272a" />
                    <stop offset="1" stopColor="#18181b" />
                </linearGradient>
            </defs>
            {BUILDINGS.map((b, bi) => {
                const top = VIEW_H - b.h;
                const cols = Math.floor((b.w - 16) / COL);
                const rows = Math.floor((b.h - 20) / ROW);
                return (
                    <g key={bi}>
                        <rect x={b.x} y={top} width={b.w} height={b.h + 2} rx={4} fill="url(#skyline-body)" stroke="rgba(255,255,255,0.06)" />
                        {Array.from({ length: rows * cols }, (_, i) => {
                            const r = Math.floor(i / cols);
                            const c = i % cols;
                            const v = hash(bi * 997 + r * 31 + c * 7 + 13);
                            const x = b.x + 10 + c * COL;
                            const y = top + 12 + r * ROW;
                            let fill = '#3f3f46';
                            let twinkle = false;
                            if (v > 905) {
                                fill = '#34d399';
                                twinkle = true;
                            } else if (v > 780) {
                                fill = '#e4e4e7';
                                twinkle = v % 3 === 0;
                            } else if (v > 560) {
                                fill = '#52525b';
                            }
                            return (
                                <rect
                                    key={i}
                                    x={x}
                                    y={y}
                                    width={8}
                                    height={9}
                                    rx={1.5}
                                    fill={fill}
                                    className={twinkle ? 'twinkle' : undefined}
                                    style={twinkle ? { animationDelay: `${(v % 40) / 10}s` } : undefined}
                                />
                            );
                        })}
                    </g>
                );
            })}
        </svg>
    );
}