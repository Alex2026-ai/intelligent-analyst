import React from 'react';
import { useScrollAnimation, useStaggeredAnimation } from '../hooks/useScrollAnimation';

/**
 * FadeIn
 *
 * Wrapper component for scroll-triggered fade-in animation.
 * Subtle, enterprise-grade effect.
 */
export function FadeIn({
  children,
  className = '',
  direction = 'up', // 'up' | 'down' | 'left' | 'right' | 'none'
  delay = 0,
  duration = 600,
}) {
  const { ref, isVisible } = useScrollAnimation();

  const directionStyles = {
    up: 'translate-y-8',
    down: '-translate-y-8',
    left: 'translate-x-8',
    right: '-translate-x-8',
    none: '',
  };

  return (
    <div
      ref={ref}
      className={`transition-all ease-out ${className}`}
      style={{
        transitionDuration: `${duration}ms`,
        transitionDelay: `${delay}ms`,
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translate(0, 0)' : undefined,
      }}
      data-animate={!isVisible ? directionStyles[direction] : ''}
    >
      <div
        className={`transition-transform ease-out`}
        style={{
          transitionDuration: `${duration}ms`,
          transitionDelay: `${delay}ms`,
          transform: isVisible ? 'none' : directionStyles[direction].replace('translate', 'translate'),
        }}
      >
        {children}
      </div>
    </div>
  );
}

/**
 * StaggeredFadeIn
 *
 * Container for staggered fade-in animations on child elements.
 */
export function StaggeredFadeIn({
  children,
  className = '',
  baseDelay = 100,
}) {
  const childArray = React.Children.toArray(children);
  const { containerRef, visibleItems } = useStaggeredAnimation(childArray.length, baseDelay);

  return (
    <div ref={containerRef} className={className}>
      {childArray.map((child, index) => (
        <div
          key={index}
          className="transition-all duration-500 ease-out"
          style={{
            opacity: visibleItems.includes(index) ? 1 : 0,
            transform: visibleItems.includes(index) ? 'translateY(0)' : 'translateY(20px)',
          }}
        >
          {child}
        </div>
      ))}
    </div>
  );
}

/**
 * AnimatedCounter
 *
 * Animated number counter for metrics.
 */
export function AnimatedCounter({ value, suffix = '', duration = 1500 }) {
  const { ref, isVisible } = useScrollAnimation();
  const [displayValue, setDisplayValue] = React.useState(0);

  React.useEffect(() => {
    if (!isVisible) return;

    const numericValue = parseInt(value.replace(/\D/g, ''), 10) || 0;
    const startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Ease-out curve
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(Math.floor(numericValue * eased));

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    animate();
  }, [isVisible, value, duration]);

  return (
    <span ref={ref}>
      {displayValue.toLocaleString()}{suffix}
    </span>
  );
}

export default FadeIn;
