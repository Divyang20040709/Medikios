import React from 'react';

interface LogoProps {
  className?: string;
  size?: number;
}

export const Logo: React.FC<LogoProps> = ({ className = "w-9 h-9", size = 36 }) => {
  return (
    <div className={`relative flex items-center justify-center ${className}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 36 36"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="transition-transform duration-300 group-hover:scale-105"
      >
        {/* Subtle Outer Glowing Kiosk Silhouette */}
        <rect
          x="3"
          y="3"
          width="30"
          height="30"
          rx="9"
          stroke="rgba(255, 255, 255, 0.25)"
          strokeWidth="1.5"
          fill="rgba(255, 255, 255, 0.03)"
        />
        
        {/* Medical Cross Geometry */}
        <path
          d="M18 9V27M9 18H27"
          stroke="white"
          strokeWidth="2.4"
          strokeLinecap="round"
        />

        {/* AI Connectivity Nodes */}
        <circle cx="18" cy="9" r="2" fill="#00F2FE" />
        <circle cx="27" cy="18" r="2" fill="#00C9A7" />
        <circle cx="18" cy="27" r="2" fill="#00F2FE" />
        <circle cx="9" cy="18" r="2" fill="#00C9A7" />

        {/* Central Core */}
        <circle cx="18" cy="18" r="3.2" fill="#060A10" stroke="white" strokeWidth="1.5" />
        <circle cx="18" cy="18" r="1.4" fill="#00F2FE" />
      </svg>
    </div>
  );
};
