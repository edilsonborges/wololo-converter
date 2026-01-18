import type { FC } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  Youtube,
  Instagram,
  Facebook,
  Twitter,
  Video,
  Music,
  Music2,
  Plus,
  X,
  Check,
  AlertTriangle,
  Download,
  ExternalLink,
  RefreshCw,
  Trash2,
  GripHorizontal,
  Inbox,
  Circle,
  Play,
  Pause,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
} from 'lucide-react';

// Icon name to component mapping
export const iconMap = {
  youtube: Youtube,
  instagram: Instagram,
  facebook: Facebook,
  twitter: Twitter,
  video: Video,
  music: Music,
  music2: Music2,
  plus: Plus,
  x: X,
  check: Check,
  alertTriangle: AlertTriangle,
  download: Download,
  externalLink: ExternalLink,
  refreshCw: RefreshCw,
  trash2: Trash2,
  gripHorizontal: GripHorizontal,
  inbox: Inbox,
  circle: Circle,
  play: Play,
  pause: Pause,
  clock: Clock,
  checkCircle: CheckCircle,
  xCircle: XCircle,
  loader2: Loader2,
} as const;

export type IconName = keyof typeof iconMap;

interface IconProps {
  name: IconName;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  strokeWidth?: number;
}

const sizeMap = {
  xs: 12,
  sm: 16,
  md: 20,
  lg: 24,
  xl: 32,
};

export const Icon: FC<IconProps> = ({
  name,
  size = 'md',
  className = '',
  strokeWidth = 1.5,
}) => {
  const IconComponent = iconMap[name] as LucideIcon;

  if (!IconComponent) {
    console.warn(`Icon "${name}" not found in icon map`);
    return null;
  }

  return (
    <IconComponent
      size={sizeMap[size]}
      strokeWidth={strokeWidth}
      className={className}
    />
  );
};

// Platform-specific icon component
interface PlatformIconProps {
  platform: string;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
}

const platformIconMap: Record<string, IconName> = {
  youtube: 'youtube',
  instagram: 'instagram',
  facebook: 'facebook',
  twitter: 'twitter',
};

export const PlatformIcon: FC<PlatformIconProps> = ({
  platform,
  size = 'md',
  className = '',
}) => {
  const iconName = platformIconMap[platform];

  if (!iconName) {
    return <Icon name="circle" size={size} className={className} />;
  }

  return <Icon name={iconName} size={size} className={className} />;
};

// Format-specific icon component
interface FormatIconProps {
  format: 'video' | 'audio_mp3' | 'audio_m4a';
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
}

const formatIconMap: Record<string, IconName> = {
  video: 'video',
  audio_mp3: 'music',
  audio_m4a: 'music2',
};

export const FormatIcon: FC<FormatIconProps> = ({
  format,
  size = 'md',
  className = '',
}) => {
  const iconName = formatIconMap[format] || 'video';
  return <Icon name={iconName} size={size} className={className} />;
};
