import React from 'react';

const stars = [
  { top: '8%', left: '10%', size: 2.6, duration: 18, delay: -4, driftX: 24, driftY: 18 },
  { top: '16%', left: '26%', size: 2, duration: 22, delay: -8, driftX: -16, driftY: 14 },
  { top: '24%', left: '73%', size: 2.8, duration: 20, delay: -3, driftX: 18, driftY: -12 },
  { top: '34%', left: '88%', size: 1.8, duration: 24, delay: -12, driftX: -22, driftY: 16 },
  { top: '43%', left: '12%', size: 2.2, duration: 19, delay: -6, driftX: 12, driftY: -14 },
  { top: '48%', left: '57%', size: 2.4, duration: 26, delay: -10, driftX: -18, driftY: 20 },
  { top: '62%', left: '35%', size: 1.9, duration: 21, delay: -7, driftX: 14, driftY: 10 },
  { top: '68%', left: '81%', size: 2.7, duration: 23, delay: -5, driftX: -20, driftY: -10 },
  { top: '78%', left: '18%', size: 2.1, duration: 25, delay: -11, driftX: 16, driftY: 12 },
  { top: '84%', left: '64%', size: 2.5, duration: 19, delay: -2, driftX: -14, driftY: -16 },
  { top: '12%', left: '55%', size: 1.7, duration: 27, delay: -9, driftX: 20, driftY: 18 },
  { top: '57%', left: '92%', size: 2.3, duration: 24, delay: -13, driftX: -16, driftY: 14 },
];

const lines = [
  { top: '18%', left: '14%', width: 180, rotate: -18, duration: 28, delay: -6, driftX: 20, driftY: 12 },
  { top: '30%', left: '58%', width: 240, rotate: 14, duration: 32, delay: -10, driftX: -18, driftY: 10 },
  { top: '56%', left: '8%', width: 210, rotate: 22, duration: 30, delay: -3, driftX: 14, driftY: -10 },
  { top: '72%', left: '54%', width: 260, rotate: -16, duration: 34, delay: -12, driftX: -22, driftY: 14 },
];

export default function BackgroundFx() {
  return (
    <div className="background-fx" aria-hidden="true">
      <div className="background-fx-gradient" />
      {lines.map((line, index) => (
        <span
          key={`line-${index}`}
          className="background-line"
          style={{
            top: line.top,
            left: line.left,
            width: `${line.width}px`,
            '--line-rotate': `${line.rotate}deg`,
            '--fx-duration': `${line.duration}s`,
            '--fx-delay': `${line.delay}s`,
            '--drift-x': `${line.driftX}px`,
            '--drift-y': `${line.driftY}px`,
          }}
        />
      ))}
      {stars.map((star, index) => (
        <span
          key={`star-${index}`}
          className="background-star"
          style={{
            top: star.top,
            left: star.left,
            width: `${star.size}px`,
            height: `${star.size}px`,
            '--fx-duration': `${star.duration}s`,
            '--fx-delay': `${star.delay}s`,
            '--drift-x': `${star.driftX}px`,
            '--drift-y': `${star.driftY}px`,
          }}
        />
      ))}
    </div>
  );
}
