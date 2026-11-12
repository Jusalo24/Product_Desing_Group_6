// Round badge logo: app name in script, slogan written around the circle.
export default function Logo() {
  return (
    <svg
      className="logo-badge"
      viewBox="0 0 240 200"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        {/* Upper arc: text sits on top of it, reading left to right. */}
        <path id="logo-top-arc" d="M 50 100 A 70 70 0 0 1 190 100" />
        {/* Lower arc: drawn under the centre so text stays upright. */}
        <path id="logo-bottom-arc" d="M 42 100 A 78 78 0 0 0 198 100" />
      </defs>

      <text className="logo-ring">
        <textPath href="#logo-top-arc" startOffset="50%" textAnchor="middle">
          EASY RECIPES
        </textPath>
      </text>
      <text className="logo-ring">
        <textPath href="#logo-bottom-arc" startOffset="50%" textAnchor="middle">
          · EASY LIFE ·
        </textPath>
      </text>

      <text x="120" y="108" textAnchor="middle" className="logo-script">
        Recipe App
      </text>

      {/* Small fork under the name */}
      <g className="logo-fork">
        <line x1="112" y1="128" x2="146" y2="128" />
        <line x1="98" y1="125" x2="110" y2="125" />
        <line x1="98" y1="128" x2="110" y2="128" />
        <line x1="98" y1="131" x2="110" y2="131" />
        <line x1="110" y1="124" x2="110" y2="132" />
      </g>
    </svg>
  );
}
